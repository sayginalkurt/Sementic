"""Google Drive — fetch dataset file (service account)."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parent
SCOPES = ("https://www.googleapis.com/auth/drive.readonly",)
DEFAULT_DATASET_FILENAME = "brand_trust_dataset.xlsx"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def drive_dataset_file_id() -> str:
    return (os.environ.get("GOOGLE_DRIVE_DATASET_FILE_ID") or "").strip()


def drive_dataset_filename() -> str:
    return (
        os.environ.get("GOOGLE_DRIVE_DATASET_FILENAME") or DEFAULT_DATASET_FILENAME
    ).strip()


def credentials_configured() -> bool:
    return _service_account_info() is not None


def drive_configured() -> bool:
    return credentials_configured() and bool(
        drive_dataset_file_id() or drive_dataset_filename()
    )


def service_account_email() -> str | None:
    info = _service_account_info()
    if not info:
        return None
    email = info.get("client_email")
    return str(email) if email else None


def _resolve_credentials_path(path: str) -> Path:
    p = Path(path)
    if p.is_file():
        return p
    candidate = ROOT / path
    if candidate.is_file():
        return candidate
    return p


def _service_account_info() -> dict[str, Any] | None:
    raw = (os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON") or "").strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON is not valid JSON."
            ) from exc

    path = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if path:
        resolved = _resolve_credentials_path(path)
        if resolved.is_file():
            with open(resolved, encoding="utf-8") as f:
                return json.load(f)
    return None


def _drive_service():
    info = _service_account_info()
    if not info:
        raise RuntimeError(
            "Google Drive credentials missing. Set GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON "
            "or GOOGLE_APPLICATION_CREDENTIALS."
        )
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_file_id_by_name(name: str | None = None) -> str | None:
    """First Drive file matching exact name visible to the service account."""
    target = (name or drive_dataset_filename()).strip()
    if not target:
        return None
    service = _drive_service()
    safe = target.replace("'", "\\'")
    query = f"name = '{safe}' and trashed = false"
    result = (
        service.files()
        .list(q=query, fields="files(id,name)", pageSize=5, supportsAllDrives=True)
        .execute()
    )
    files = result.get("files") or []
    return str(files[0]["id"]) if files else None


def resolve_dataset_file_id() -> str:
    fid = drive_dataset_file_id()
    if fid:
        return fid
    found = find_file_id_by_name()
    if found:
        return found
    email = service_account_email() or "service-account@project.iam.gserviceaccount.com"
    raise RuntimeError(
        f"Dataset file '{drive_dataset_filename()}' not found on Drive. "
        f"Share it with {email} (Viewer) and/or set GOOGLE_DRIVE_DATASET_FILE_ID."
    )


def _download_request(service, file_id: str):
    """Native xlsx or Google Sheet exported as xlsx."""
    meta = (
        service.files()
        .get(fileId=file_id, fields="mimeType,name", supportsAllDrives=True)
        .execute()
    )
    mime = meta.get("mimeType") or ""
    if mime == MIME_GOOGLE_SHEET:
        return service.files().export_media(fileId=file_id, mimeType=MIME_XLSX)
    return service.files().get_media(fileId=file_id, supportsAllDrives=True)


def fetch_drive_file_bytes(file_id: str | None = None) -> bytes:
    """Download a Drive file by ID (xlsx or Google Sheet → xlsx export)."""
    fid = (file_id or resolve_dataset_file_id()).strip()

    service = _drive_service()
    request = _download_request(service, fid)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()
