"""Brand trust dataset — local file or Google Drive xlsx."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from google_drive import drive_configured, fetch_drive_file_bytes

ROOT = Path(__file__).resolve().parent
DEFAULT_LOCAL_PATH = ROOT / "brand_trust_dataset.xlsx"
RESPONDENTS_SHEET = "Respondents"
RESPONDENT_ID_COL = "respondent_id"
OPEN_ENDED_COL = "open_ended_response"

LIST_COLUMNS = [
    "respondent_id",
    "age",
    "gender",
    "education",
    "income_group",
    "hidden_segment",
    "n_concepts",
    "n_relationships",
]

_cache: dict[str, Any] = {"bytes": None, "source": None}


def dataset_path() -> Path:
    custom = (os.environ.get("DATASET_PATH") or "").strip()
    return Path(custom) if custom else DEFAULT_LOCAL_PATH


def dataset_source() -> str:
    """local | drive | none — reflects last successful load preference."""
    if drive_configured():
        return "drive"
    if dataset_path().is_file():
        return "local"
    return "none"


def dataset_configured() -> bool:
    return dataset_source() != "none"


def _load_bytes() -> tuple[bytes, str]:
    if drive_configured():
        try:
            return fetch_drive_file_bytes(), "drive"
        except Exception:
            path = dataset_path()
            if path.is_file():
                return path.read_bytes(), "local"
            raise
    path = dataset_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset not found at {path}. Set DATASET_PATH, place "
            f"{DEFAULT_LOCAL_PATH.name} locally, or configure Google Drive."
        )
    return path.read_bytes(), "local"


def _get_workbook_bytes() -> tuple[bytes, str]:
    global _cache
    data, source = _load_bytes()
    if _cache["bytes"] != data or _cache["source"] != source:
        _cache = {"bytes": data, "source": source}
    return data, source


def clear_dataset_cache() -> None:
    global _cache
    _cache = {"bytes": None, "source": None}


def _read_respondents_df() -> pd.DataFrame:
    data, _source = _get_workbook_bytes()
    df = pd.read_excel(BytesIO(data), sheet_name=RESPONDENTS_SHEET)
    if RESPONDENT_ID_COL not in df.columns:
        raise ValueError(f"Sheet '{RESPONDENTS_SHEET}' missing '{RESPONDENT_ID_COL}' column.")
    if OPEN_ENDED_COL not in df.columns:
        raise ValueError(f"Sheet '{RESPONDENTS_SHEET}' missing '{OPEN_ENDED_COL}' column.")
    return df


def _row_to_dict(row: pd.Series, *, include_text: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in row.index:
        val = row[col]
        if pd.isna(val):
            out[str(col)] = None
        elif isinstance(val, (int, float)) and col != OPEN_ENDED_COL:
            out[str(col)] = int(val) if float(val).is_integer() else float(val)
        else:
            out[str(col)] = str(val)
    text = (out.get(OPEN_ENDED_COL) or "").strip()
    if include_text:
        out[OPEN_ENDED_COL] = text
    else:
        out["open_ended_preview"] = text[:160] + ("…" if len(text) > 160 else "")
        out.pop(OPEN_ENDED_COL, None)
    return out


def list_respondents(*, q: str | None = None) -> dict[str, Any]:
    df = _read_respondents_df()
    _, source = _get_workbook_bytes()

    if q:
        needle = q.strip().lower()
        mask = df.apply(
            lambda r: any(
                needle in str(v).lower()
                for v in r.values
                if v is not None and not (isinstance(v, float) and pd.isna(v))
            ),
            axis=1,
        )
        df = df[mask]

    items = []
    for _, row in df.iterrows():
        parsed = _row_to_dict(row, include_text=False)
        item = {k: parsed.get(k) for k in LIST_COLUMNS}
        item["open_ended_preview"] = parsed.get("open_ended_preview")
        items.append(item)

    return {
        "source": source,
        "count": len(items),
        "respondents": items,
    }


def get_respondent(respondent_id: str) -> dict[str, Any]:
    df = _read_respondents_df()
    _, source = _get_workbook_bytes()
    rid = respondent_id.strip()
    match = df[df[RESPONDENT_ID_COL].astype(str) == rid]
    if match.empty:
        raise ValueError(f"Respondent '{rid}' not found.")
    row = match.iloc[0]
    return {"source": source, "respondent": _row_to_dict(row, include_text=True)}


def get_open_ended_response(respondent_id: str) -> str:
    rec = get_respondent(respondent_id)["respondent"]
    text = (rec.get(OPEN_ENDED_COL) or "").strip()
    if not text:
        raise ValueError(f"Respondent '{respondent_id}' has no open-ended response.")
    return text
