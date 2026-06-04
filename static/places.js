/**
 * Google Maps place picker, review fetch, and per-review Sementic analysis.
 */

import { renderReviewAnalyses, clearReviewAnalyses } from "./review-analyses.js";

const placesUi = document.getElementById("places-ui");
const placesConfigMsg = document.getElementById("places-config-msg");
const placeSearch = document.getElementById("place-search");
const placeMapEl = document.getElementById("place-map");
const placeMeta = document.getElementById("place-meta");
const placesLoading = document.getElementById("places-loading");
const reviewsPanel = document.getElementById("reviews-panel");
const reviewsList = document.getElementById("reviews-list");
const reviewsCount = document.getElementById("reviews-count");
const reviewsLimitNote = document.getElementById("reviews-limit-note");
const analyzeReviewsBtn = document.getElementById("analyze-reviews-btn");
const placesAnalyzeLoading = document.getElementById("places-analyze-loading");
const reviewAnalysesRoot = document.getElementById("review-analyses-root");

let map = null;
let lastPlaceData = null;
let marker = null;
let autocomplete = null;
let selectedPlaceId = null;

function showPlacesMessage(text, isError = false) {
  placesConfigMsg.hidden = !text;
  placesConfigMsg.textContent = text || "";
  placesConfigMsg.classList.toggle("error", isError);
}

function loadGoogleMaps(apiKey) {
  return new Promise((resolve, reject) => {
    if (window.google?.maps?.places) {
      resolve();
      return;
    }
    const cbName = "__sementicMapsReady";
    window[cbName] = () => {
      delete window[cbName];
      resolve();
    };
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=places&callback=${cbName}`;
    script.async = true;
    script.defer = true;
    script.onerror = () => reject(new Error("Failed to load Google Maps JavaScript API"));
    document.head.appendChild(script);
  });
}

function initMap() {
  const center = { lat: 41.0082, lng: 28.9784 };
  map = new google.maps.Map(placeMapEl, {
    center,
    zoom: 12,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true,
  });
  marker = new google.maps.Marker({ map, position: center, visible: false });
}

function initAutocomplete() {
  autocomplete = new google.maps.places.Autocomplete(placeSearch, {
    fields: ["place_id", "name", "formatted_address", "geometry", "rating", "user_ratings_total"],
  });
  autocomplete.bindTo("bounds", map);

  autocomplete.addListener("place_changed", () => {
    const place = autocomplete.getPlace();
    if (!place.place_id) {
      showPlacesMessage("No place selected. Pick a suggestion from the list.", true);
      return;
    }
    selectedPlaceId = place.place_id;
    showPlacesMessage("");

    if (place.geometry?.location) {
      map.panTo(place.geometry.location);
      map.setZoom(15);
      marker.setPosition(place.geometry.location);
      marker.setVisible(true);
    }

    const rating =
      place.rating != null ? ` · ${place.rating}★` : "";
    const total =
      place.user_ratings_total != null ? ` (${place.user_ratings_total} ratings)` : "";
    placeMeta.hidden = false;
    placeMeta.innerHTML = `<strong>${escapeHtml(place.name || "Place")}</strong><br /><span class="hint">${escapeHtml(place.formatted_address || "")}${rating}${total}</span>`;

    fetchReviews(place.place_id);
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function fetchReviews(placeId) {
  reviewsPanel.hidden = true;
  reviewsList.innerHTML = "";
  clearReviewAnalyses(reviewAnalysesRoot);
  analyzeReviewsBtn.disabled = true;
  placesLoading.hidden = false;

  try {
    const res = await fetch(`/api/places/${encodeURIComponent(placeId)}/reviews`);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Failed to load reviews");

    lastPlaceData = data;
    renderReviews(data);
    analyzeReviewsBtn.disabled = !(data.reviews && data.reviews.length);
  } catch (err) {
    showPlacesMessage(err.message || String(err), true);
  } finally {
    placesLoading.hidden = true;
  }
}

function renderReviews(data) {
  const reviews = data.reviews || [];
  reviewsCount.textContent = reviews.length ? `(${reviews.length})` : "";

  if (!reviews.length) {
    reviewsList.innerHTML = "<li class='reviews-empty'>No review text returned for this place.</li>";
  } else {
    reviews.forEach((r) => {
      const li = document.createElement("li");
      const stars = r.rating != null ? `${r.rating}★ · ` : "";
      const when = r.relative_time ? ` · ${r.relative_time}` : "";
      const author = r.author ? `<span class="review-author">${escapeHtml(r.author)}</span>` : "";
      li.innerHTML = `${author}<span class="review-meta">${stars}${when}</span><p>${escapeHtml(r.text)}</p>`;
      reviewsList.appendChild(li);
    });
  }

  reviewsPanel.hidden = false;

  if (data.user_ratings_total != null && reviews.length) {
    reviewsLimitNote.hidden = false;
    reviewsLimitNote.textContent = `Showing ${reviews.length} of ${data.user_ratings_total} ratings (Google API text limit).`;
  } else {
    reviewsLimitNote.hidden = true;
  }

  if (data.google_maps_uri) {
    const link = document.createElement("a");
    link.href = data.google_maps_uri;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.className = "review-maps-link";
    link.textContent = "Open in Google Maps";
    placeMeta.appendChild(document.createElement("br"));
    placeMeta.appendChild(link);
  }
}

analyzeReviewsBtn.addEventListener("click", async () => {
  if (!selectedPlaceId) {
    showPlacesMessage("Select a place first.", true);
    return;
  }

  showPlacesMessage("");
  clearReviewAnalyses(reviewAnalysesRoot);
  analyzeReviewsBtn.disabled = true;
  placesAnalyzeLoading.hidden = false;

  const fd = new FormData();
  fd.append("min_freq", document.getElementById("min-freq")?.value ?? "0");

  try {
    const res = await fetch(
      `/api/places/${encodeURIComponent(selectedPlaceId)}/analyze-reviews`,
      { method: "POST", body: fd }
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Review analysis failed");

    renderReviewAnalyses(data, reviewAnalysesRoot);
    reviewAnalysesRoot.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showPlacesMessage(err.message || String(err), true);
  } finally {
    placesAnalyzeLoading.hidden = true;
    analyzeReviewsBtn.disabled = !!(lastPlaceData?.reviews?.length);
  }
});

async function bootstrap() {
  try {
    const res = await fetch("/api/places/config");
    const cfg = await res.json();

    if (!cfg.maps_js_enabled || !cfg.maps_api_key) {
      showPlacesMessage(
        "Set GOOGLE_MAPS_API_KEY in .env (Maps JavaScript API + Places API enabled).",
        true
      );
      return;
    }

    if (!cfg.places_api_enabled) {
      showPlacesMessage(
        "Maps key found; set GOOGLE_PLACES_API_KEY for server review fetch (or reuse the same key).",
        true
      );
    }

    await loadGoogleMaps(cfg.maps_api_key);
    placesUi.hidden = false;
    initMap();
    initAutocomplete();
  } catch (err) {
    showPlacesMessage(err.message || String(err), true);
  }
}

bootstrap();
