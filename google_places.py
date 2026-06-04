"""Google Places API — place details and customer reviews (not wired to analysis)."""

from __future__ import annotations

import os
from typing import Any

import httpx

PLACES_V1_BASE = "https://places.googleapis.com/v1/places"
LEGACY_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

FIELD_MASK = (
    "id,displayName,formattedAddress,rating,userRatingCount,reviews,"
    "googleMapsUri"
)


def maps_api_key() -> str:
    return (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()


def places_api_key() -> str:
    """Server-side Places key; falls back to Maps key if dedicated key unset."""
    return (os.environ.get("GOOGLE_PLACES_API_KEY") or maps_api_key()).strip()


def _normalize_place_id(place_id: str) -> str:
    pid = place_id.strip()
    if pid.startswith("places/"):
        return pid[len("places/") :]
    return pid


def _parse_new_api_reviews(data: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in data.get("reviews") or []:
        if not isinstance(item, dict):
            continue
        text_obj = item.get("text") or {}
        text = text_obj.get("text") if isinstance(text_obj, dict) else str(text_obj or "")
        author = item.get("authorAttribution") or {}
        out.append(
            {
                "author": author.get("displayName") if isinstance(author, dict) else None,
                "rating": item.get("rating"),
                "text": (text or "").strip(),
                "relative_time": item.get("relativePublishTimeDescription"),
                "published_at": item.get("publishTime"),
            }
        )
    return [r for r in out if r.get("text")]


def _parse_legacy_reviews(result: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in result.get("reviews") or []:
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        out.append(
            {
                "author": item.get("author_name"),
                "rating": item.get("rating"),
                "text": text,
                "relative_time": item.get("relative_time_description"),
                "published_at": item.get("time"),
            }
        )
    return [r for r in out if r.get("text")]


async def _fetch_new_api(place_id: str, api_key: str) -> dict[str, Any]:
    pid = _normalize_place_id(place_id)
    url = f"{PLACES_V1_BASE}/{pid}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def _fetch_legacy_api(place_id: str, api_key: str) -> dict[str, Any]:
    pid = _normalize_place_id(place_id)
    params = {
        "place_id": pid,
        "fields": "place_id,name,formatted_address,rating,user_ratings_total,reviews,url",
        "key": api_key,
        "reviews_no_translations": "true",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(LEGACY_DETAILS_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    status = payload.get("status")
    if status and status != "OK":
        msg = payload.get("error_message") or status
        raise ValueError(f"Google Places API: {msg}")
    return payload.get("result") or {}


def _payload_from_new(data: dict[str, Any], place_id: str) -> dict[str, Any]:
    name_obj = data.get("displayName") or {}
    name = name_obj.get("text") if isinstance(name_obj, dict) else str(name_obj or "")
    reviews = _parse_new_api_reviews(data)
    return {
        "place_id": place_id,
        "name": name or None,
        "address": data.get("formattedAddress"),
        "rating": data.get("rating"),
        "user_ratings_total": data.get("userRatingCount"),
        "google_maps_uri": data.get("googleMapsUri"),
        "reviews": reviews,
        "review_count": len(reviews),
        "source": "places_v1",
    }


def _payload_from_legacy(result: dict[str, Any], place_id: str) -> dict[str, Any]:
    reviews = _parse_legacy_reviews(result)
    return {
        "place_id": result.get("place_id") or place_id,
        "name": result.get("name"),
        "address": result.get("formatted_address"),
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total"),
        "google_maps_uri": result.get("url"),
        "reviews": reviews,
        "review_count": len(reviews),
        "source": "legacy",
    }


async def fetch_place_reviews(place_id: str) -> dict[str, Any]:
    """
    Fetch place metadata and up to ~5 most relevant Google reviews.
    Tries Places API (New) first, then legacy Place Details.
    """
    api_key = places_api_key()
    if not api_key:
        raise RuntimeError(
            "Google API key not configured. Set GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY in .env"
        )

    pid = _normalize_place_id(place_id)
    if not pid:
        raise ValueError("place_id is required")

    errors: list[str] = []

    try:
        data = await _fetch_new_api(pid, api_key)
        return _payload_from_new(data, pid)
    except httpx.HTTPStatusError as exc:
        errors.append(f"Places API (New): HTTP {exc.response.status_code}")
    except Exception as exc:
        errors.append(f"Places API (New): {exc}")

    try:
        result = await _fetch_legacy_api(pid, api_key)
        return _payload_from_legacy(result, pid)
    except Exception as exc:
        errors.append(f"Legacy Place Details: {exc}")

    raise RuntimeError("; ".join(errors))
