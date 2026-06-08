# Dataset channel (Google Drive / local)

Load **brand_trust_dataset.xlsx** from Google Drive or a local path. The **Respondents** sheet is listed in CH-C; each row's `open_ended_response` can be analyzed with STAT-3NET or FCM.

## Sheets used

| Sheet | Use |
|-------|-----|
| `Respondents` | List + `open_ended_response` for analysis |
| `Relationships`, `Concepts` | Not used yet |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/dataset/config` | `configured`, `source` (`local` \| `drive` \| `none`) |
| `GET /api/dataset/respondents?q=` | Respondent list (preview text only) |
| `GET /api/dataset/respondents/{id}` | Full row |
| `POST /api/dataset/respondents/{id}/analyze` | Form: `min_freq`, `pipeline` |
| `POST /api/dataset/respondents/{id}/analyze/stream` | NDJSON progress stream |

## Local setup

1. Place `brand_trust_dataset.xlsx` in the project root, or set `DATASET_PATH`.
2. No Drive credentials needed.

## Google Drive setup (Railway)

Requires a **Google Cloud service account** with Drive API enabled.

1. Enable **Google Drive API** in Google Cloud Console.
2. Create a service account → download JSON key.
3. Share the dataset file with the service account email as **Viewer**.
4. Set Railway variables:

| Variable | Description |
|----------|-------------|
| `GOOGLE_DRIVE_DATASET_FILE_ID` | File ID from Drive URL |
| `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` | Full JSON key (single line) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Alternative: path to JSON file (local) |

### Source priority

If Drive credentials + file ID are set, **Drive wins** over the local file.

Google Sheets are exported as xlsx automatically on download.

## Code layout

| File | Role |
|------|------|
| `dataset.py` | xlsx loader, respondent queries |
| `google_drive.py` | Service account download |
| `app.py` | `/api/dataset/*` routes |
| `static/dataset.js` | CH-C UI |
