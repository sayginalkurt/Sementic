"""Sementic — ağ analizi web uygulaması."""

from __future__ import annotations

import asyncio
import io
import json
import os
import queue
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

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
from dataset import (
    dataset_configured,
    dataset_source,
    get_open_ended_response,
    get_respondent,
    list_respondents,
)
from fcm_service import run_fcm_analysis
from google_drive import credentials_configured, drive_configured, service_account_email
from google_places import fetch_place_reviews, maps_api_key, places_api_key
from workflow import emit, normalize_pipeline, progress_event

STATIC = ROOT / "static"

app = FastAPI(title="Sementic Analysis Tool", version="0.00001")
app.add_middleware(AppPasswordMiddleware)
register_auth_routes(app)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AnalyzeBody(BaseModel):
    text: str = Field(..., min_length=20)
    min_freq: int = Field(0, ge=0, le=10)
    pipeline: str = Field("statistical")


class DownloadBody(BaseModel):
    labels: list[str]
    values: list[list[float]]
    filename: str = "matrix.xlsx"


ProgressFn = Callable[[str, str, dict[str, Any] | None], None]


def _run_pipeline(
    raw_text: str,
    *,
    min_freq: int = 0,
    pipeline: str = "statistical",
    on_progress: ProgressFn | None = None,
    review_index: int | None = None,
) -> dict:
    mode = normalize_pipeline(pipeline)
    if mode == "fcm":
        return run_fcm_analysis(
            raw_text,
            on_progress=on_progress,
            review_index=review_index,
        )
    return run_sementic_analysis(
        raw_text,
        min_freq=min_freq,
        on_progress=on_progress,
        review_index=review_index,
    )


def _ndjson_stream(worker: Callable[[ProgressFn], Any]) -> StreamingResponse:
    """Run sync pipeline in a thread; stream progress events as NDJSON."""

    def generate() -> Iterator[str]:
        q: queue.SimpleQueue = queue.SimpleQueue()

        def on_progress(step: str, status: str, detail: dict[str, Any] | None = None) -> None:
            q.put(progress_event(step, status, detail))

        def run() -> None:
            try:
                result = worker(on_progress)
                q.put({"type": "result", "data": result})
            except Exception as exc:
                q.put({"type": "error", "detail": str(exc)})
            finally:
                q.put(None)

        threading.Thread(target=run, daemon=True).start()

        while True:
            item = q.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    try:
        ds_configured = dataset_configured()
        ds_source = dataset_source()
    except Exception:
        ds_configured = False
        ds_source = "none"
    return {
        "ok": True,
        "openai_configured": bool(key),
        "google_maps_configured": bool(maps_api_key()),
        "google_places_configured": bool(places_api_key()),
        "auth_required": auth_enabled(),
        "dataset_configured": ds_configured,
        "dataset_source": ds_source,
    }


@app.get("/api/dataset/config")
async def dataset_config() -> dict:
    return {
        "configured": dataset_configured(),
        "source": dataset_source(),
        "drive_configured": drive_configured(),
        "drive_credentials": credentials_configured(),
        "service_account_email": service_account_email(),
    }


@app.get("/api/dataset/respondents")
async def dataset_respondents(q: str | None = None) -> dict:
    if not dataset_configured():
        raise HTTPException(
            503,
            "Dataset not configured. Use local DATASET_PATH or Google Drive env vars.",
        )
    try:
        return list_respondents(q=q)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Dataset error: {exc}") from exc


@app.get("/api/dataset/respondents/{respondent_id}")
async def dataset_respondent(respondent_id: str) -> dict:
    if not dataset_configured():
        raise HTTPException(503, "Dataset not configured.")
    try:
        return get_respondent(respondent_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Dataset error: {exc}") from exc


def _analyze_dataset_payload(
    respondent_id: str,
    *,
    min_freq: int,
    pipeline: str,
    on_progress: ProgressFn | None = None,
) -> dict:
    respondent_payload = get_respondent(respondent_id)
    text = get_open_ended_response(respondent_id)
    analysis = _run_pipeline(
        text,
        min_freq=min_freq,
        pipeline=pipeline,
        on_progress=on_progress,
    )
    return {
        "respondent": respondent_payload["respondent"],
        "source": respondent_payload["source"],
        "pipeline": normalize_pipeline(pipeline),
        "analysis": analysis,
    }


@app.post("/api/dataset/respondents/{respondent_id}/analyze/stream")
async def analyze_dataset_respondent_stream(
    respondent_id: str,
    min_freq: int = Form(0),
    pipeline: str = Form("statistical"),
) -> StreamingResponse:
    if not dataset_configured():
        raise HTTPException(503, "Dataset not configured.")

    captured_id = respondent_id
    captured_freq = min_freq
    captured_pipeline = normalize_pipeline(pipeline)

    def work(on_progress: ProgressFn) -> dict:
        return _analyze_dataset_payload(
            captured_id,
            min_freq=captured_freq,
            pipeline=captured_pipeline,
            on_progress=on_progress,
        )

    return _ndjson_stream(work)


@app.post("/api/dataset/respondents/{respondent_id}/analyze")
async def analyze_dataset_respondent(
    respondent_id: str,
    min_freq: int = Form(0),
    pipeline: str = Form("statistical"),
) -> dict:
    if not dataset_configured():
        raise HTTPException(503, "Dataset not configured.")
    try:
        return _analyze_dataset_payload(
            respondent_id,
            min_freq=min_freq,
            pipeline=pipeline,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Analysis error: {exc}") from exc


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


def _analyze_reviews_payload(
    place: dict,
    *,
    min_freq: int,
    pipeline: str = "statistical",
    on_progress: ProgressFn | None = None,
) -> dict:
    analyses: list[dict] = []
    analyzed_count = 0
    skipped_count = 0
    reviews = place.get("reviews") or []

    emit(
        on_progress,
        "batch_dispatch",
        "running",
        {"reviews": len(reviews)},
    )

    for i, review in enumerate(reviews):
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
            result = _run_pipeline(
                text,
                min_freq=min_freq,
                pipeline=pipeline,
                on_progress=on_progress,
                review_index=i,
            )
            analyzed_count += 1
            analyses.append(
                {
                    "review_index": i,
                    "review": review,
                    "skipped": False,
                    "analysis": result,
                }
            )
        except RuntimeError:
            raise
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
        raise ValueError("No reviews returned for this place.")

    emit(
        on_progress,
        "batch_complete",
        "done",
        {"analyzed": analyzed_count, "skipped": skipped_count},
    )

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
        "pipeline": normalize_pipeline(pipeline),
    }


@app.post("/api/places/{place_id}/analyze-reviews/stream")
async def analyze_place_reviews_stream(
    place_id: str,
    min_freq: int = Form(0),
    pipeline: str = Form("statistical"),
) -> StreamingResponse:
    captured_id = place_id
    captured_freq = min_freq
    captured_pipeline = normalize_pipeline(pipeline)

    def work(on_progress: ProgressFn) -> dict:
        emit(on_progress, "place_fetch", "running", {"place_id": captured_id})
        place = asyncio.run(fetch_place_reviews(captured_id))
        emit(
            on_progress,
            "place_fetch",
            "done",
            {"reviews": len(place.get("reviews") or [])},
        )
        return _analyze_reviews_payload(
            place,
            min_freq=captured_freq,
            pipeline=captured_pipeline,
            on_progress=on_progress,
        )

    return _ndjson_stream(work)


@app.post("/api/places/{place_id}/analyze-reviews")
async def analyze_place_reviews(
    place_id: str,
    min_freq: int = Form(0),
    pipeline: str = Form("statistical"),
) -> dict:
    """
    Fetch up to 5 Google reviews, run full Sementic analysis on each review text separately.
    """
    try:
        place = await fetch_place_reviews(place_id)
        return _analyze_reviews_payload(
            place, min_freq=min_freq, pipeline=pipeline
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        code = 400 if "shorter than" in msg else 422
        raise HTTPException(code, msg) from exc
    except Exception as exc:
        raise HTTPException(502, f"Google Places error: {exc}") from exc


@app.post("/api/analyze/stream")
async def analyze_stream(
    text: str | None = Form(None),
    min_freq: int = Form(0),
    pipeline: str = Form("statistical"),
    file: UploadFile | None = File(None),
) -> StreamingResponse:
    raw = (text or "").strip()
    if file and file.filename:
        payload = await file.read()
        raw = payload.decode("utf-8", errors="replace").strip()
    if len(raw) < MIN_ANALYSIS_TEXT_LEN:
        raise HTTPException(
            400,
            f"En az {MIN_ANALYSIS_TEXT_LEN} karakter metin veya dosya gerekli.",
        )

    captured = raw
    captured_pipeline = normalize_pipeline(pipeline)

    def work(on_progress: ProgressFn) -> dict:
        return _run_pipeline(
            captured,
            min_freq=min_freq,
            pipeline=captured_pipeline,
            on_progress=on_progress,
        )

    return _ndjson_stream(work)


@app.post("/api/analyze")
async def analyze(
    text: str | None = Form(None),
    min_freq: int = Form(0),
    pipeline: str = Form("statistical"),
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
        return _run_pipeline(
            raw, min_freq=min_freq, pipeline=pipeline
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Analysis error: {exc}") from exc


@app.post("/api/analyze/json")
async def analyze_json(body: AnalyzeBody) -> dict:
    try:
        return _run_pipeline(
            body.text,
            min_freq=body.min_freq,
            pipeline=body.pipeline,
        )
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
