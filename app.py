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

from ai_preprocess import concepts_preview, extract_concepts_with_ai
from analyses import dataframe_to_payload, run_all_analyses_from_sentences
from graph import graphs_from_matrices

STATIC = ROOT / "static"

app = FastAPI(title="Sementic Analysis Tool", version="0.00001")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class AnalyzeBody(BaseModel):
    text: str = Field(..., min_length=20)
    min_freq: int = Field(2, ge=1, le=10)


class DownloadBody(BaseModel):
    labels: list[str]
    values: list[list[float]]
    filename: str = "matrix.csv"


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/sample")
async def sample_text() -> FileResponse:
    path = ROOT / "testdata.txt"
    if not path.is_file():
        raise HTTPException(404, "testdata.txt bulunamadı.")
    return FileResponse(path, media_type="text/plain; charset=utf-8")


@app.get("/api/health")
async def health() -> dict:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    return {
        "ok": True,
        "openai_configured": bool(key),
    }


@app.post("/api/analyze")
async def analyze(
    text: str | None = Form(None),
    min_freq: int = Form(2),
    file: UploadFile | None = File(None),
) -> dict:
    raw = (text or "").strip()
    if file and file.filename:
        payload = await file.read()
        raw = payload.decode("utf-8", errors="replace").strip()
    if len(raw) < 20:
        raise HTTPException(400, "En az 20 karakter metin veya dosya gerekli.")

    try:
        sentences, concept_list = extract_concepts_with_ai(raw)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"AI işleme hatası: {exc}") from exc

    try:
        vocab, matrices = run_all_analyses_from_sentences(
            sentences, min_freq=min_freq
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    matrix_payload = {
        key: dataframe_to_payload(df) for key, df in matrices.items()
    }
    return {
        "sentence_count": len(sentences),
        "vocabulary_size": len(vocab),
        "vocabulary": vocab,
        "concepts_by_sentence": sentences,
        "concept_frequency": concepts_preview(sentences),
        "matrices": matrix_payload,
        "graphs": graphs_from_matrices(matrix_payload),
        "matrix_labels": {
            "cooccurrence": "Eş-Oluşum (Co-occurrence)",
            "semantic": "Anlamsal (Semantic)",
            "epistemic": "Epistemik (ENA)",
        },
    }


@app.post("/api/analyze/json")
async def analyze_json(body: AnalyzeBody) -> dict:
    try:
        sentences, _ = extract_concepts_with_ai(body.text)
        vocab, matrices = run_all_analyses_from_sentences(
            sentences, min_freq=body.min_freq
        )
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"AI işleme hatası: {exc}") from exc

    matrix_payload = {
        key: dataframe_to_payload(df) for key, df in matrices.items()
    }
    return {
        "sentence_count": len(sentences),
        "vocabulary_size": len(vocab),
        "vocabulary": vocab,
        "concepts_by_sentence": sentences,
        "concept_frequency": concepts_preview(sentences),
        "matrices": matrix_payload,
        "graphs": graphs_from_matrices(matrix_payload),
    }


@app.post("/api/download/csv")
async def download_csv(body: DownloadBody) -> StreamingResponse:
    if not body.labels or not body.values:
        raise HTTPException(400, "Boş matris indirilemez.")
    import pandas as pd

    df = pd.DataFrame(body.values, index=body.labels, columns=body.labels)
    buf = io.StringIO()
    df.to_csv(buf, encoding="utf-8-sig")
    buf.seek(0)
    name = body.filename if body.filename.endswith(".csv") else f"{body.filename}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
