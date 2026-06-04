"""Sementic — ağ analizi web uygulaması."""

from __future__ import annotations

import io
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
# Shell'deki eski OPENAI_API_KEY yerine proje .env kullanılır
load_dotenv(ROOT / ".env", override=True)

from analysis_service import MIN_ANALYSIS_TEXT_LEN, run_sementic_analysis
from auth import AppPasswordMiddleware, auth_enabled, register_auth_routes
from google_places import fetch_place_reviews, maps_api_key, places_api_key

STATIC = ROOT / "static"

app = FastAPI(title="Sementic Analysis Tool", version="0.00001")
app.add_middleware(AppPasswordMiddleware)
register_auth_routes(app)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AnalyzeBody(BaseModel):
    text: str = Field(..., min_length=20)
    min_freq: int = Field(0, ge=0, le=10)


class DownloadBody(BaseModel):
    labels: list[str]
    values: list[list[float]]
    filename: str = "matrix.xlsx"


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    return {
        "ok": True,
        "openai_configured": bool(key),
        "google_maps_configured": bool(maps_api_key()),
        "google_places_configured": bool(places_api_key()),
        "auth_required": auth_enabled(),
    }


@app.get("/api/places/config")
async def places_config() -> dict:
    """Public Maps JS key + flags for the place picker (browser)."""
    mk = maps_api_key()
    return {
        "maps_js_enabled": bool(mk),
        "places_api_enabled": bool(places_api_key()),
        "maps_api_key": mk or None,
    }


@app.get("/api/places/{place_id}/reviews")
async def place_reviews(place_id: str) -> dict:
    """Fetch Google reviews for a place_id."""
    try:
        return await fetch_place_reviews(place_id)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Google Places error: {exc}") from exc


@app.post("/api/places/{place_id}/analyze-reviews")
async def analyze_place_reviews(
    place_id: str,
    min_freq: int = Form(0),
) -> dict:
    """
    Fetch up to 5 Google reviews, run full Sementic analysis on each review text separately.
    """
    try:
        place = await fetch_place_reviews(place_id)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Google Places error: {exc}") from exc

    analyses: list[dict] = []
    analyzed_count = 0
    skipped_count = 0

    for i, review in enumerate(place.get("reviews") or []):
        text = (review.get("text") or "").strip()
        if len(text) < MIN_ANALYSIS_TEXT_LEN:
            skipped_count += 1
            analyses.append(
                {
                    "review_index": i,
                    "review": review,
                    "skipped": True,
                    "reason": (
                        f"Review text shorter than {MIN_ANALYSIS_TEXT_LEN} characters."
                    ),
                }
            )
            continue

        try:
            result = run_sementic_analysis(text, min_freq=min_freq)
            analyzed_count += 1
            analyses.append(
                {
                    "review_index": i,
                    "review": review,
                    "skipped": False,
                    "analysis": result,
                }
            )
        except RuntimeError as exc:
            raise HTTPException(503, str(exc)) from exc
        except ValueError as exc:
            analyses.append(
                {
                    "review_index": i,
                    "review": review,
                    "skipped": True,
                    "reason": str(exc),
                }
            )
            skipped_count += 1
        except Exception as exc:
            analyses.append(
                {
                    "review_index": i,
                    "review": review,
                    "skipped": True,
                    "error": str(exc),
                }
            )
            skipped_count += 1

    if not analyses:
        raise HTTPException(422, "No reviews returned for this place.")

    return {
        "place": {
            "place_id": place.get("place_id"),
            "name": place.get("name"),
            "address": place.get("address"),
            "rating": place.get("rating"),
            "user_ratings_total": place.get("user_ratings_total"),
            "review_count": place.get("review_count"),
            "reviews_limit_note": (
                "Google Places API returns at most 5 review texts per place."
            ),
        },
        "analyses": analyses,
        "analyzed_count": analyzed_count,
        "skipped_count": skipped_count,
    }


@app.post("/api/analyze")
async def analyze(
    text: str | None = Form(None),
    min_freq: int = Form(0),
    file: UploadFile | None = File(None),
) -> dict:
    raw = (text or "").strip()
    if file and file.filename:
        payload = await file.read()
        raw = payload.decode("utf-8", errors="replace").strip()
    if len(raw) < MIN_ANALYSIS_TEXT_LEN:
        raise HTTPException(
            400,
            f"En az {MIN_ANALYSIS_TEXT_LEN} karakter metin veya dosya gerekli.",
        )

    try:
        return run_sementic_analysis(raw, min_freq=min_freq)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Analysis error: {exc}") from exc


@app.post("/api/analyze/json")
async def analyze_json(body: AnalyzeBody) -> dict:
    try:
        return run_sementic_analysis(body.text, min_freq=body.min_freq)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Analysis error: {exc}") from exc


@app.post("/api/download/xlsx")
async def download_xlsx(body: DownloadBody) -> StreamingResponse:
    if not body.labels or not body.values:
        raise HTTPException(400, "Boş matris indirilemez.")
    import pandas as pd

    df = pd.DataFrame(body.values, index=body.labels, columns=body.labels)
    buf = io.BytesIO()
    df.to_excel(buf, engine="openpyxl")
    buf.seek(0)
    name = body.filename if body.filename.endswith(".xlsx") else f"{body.filename}.xlsx"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
