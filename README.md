# Sementic Analysis Tool

Thematic concept extraction (OpenAI) and three network analyses: **co-occurrence**, **semantic**, and **epistemic (ENA-style)**. Web UI with matrices, interactive graphs (PNG export), and XLSX export.

**Version:** v0.00001

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY
uvicorn app:app --reload --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Railway deployment

1. Push this repo to GitHub (see below).
2. [Railway](https://railway.app) → **New Project** → **Deploy from GitHub repo**.
3. **Variables** (required):

   | Variable | Description |
   |----------|-------------|
   | `OPENAI_API_KEY` | Your OpenAI API key |
   | `OPENAI_MODEL` | Optional, e.g. `gpt-4o-mini` |
| `GOOGLE_MAPS_API_KEY` | Maps place picker (browser) |
| `GOOGLE_PLACES_API_KEY` | Optional; server review fetch (defaults to Maps key) |
| `APP_PASSWORD` | App login password (required on Railway; empty = no gate locally) |

4. Railway sets `PORT` automatically; the app binds to `0.0.0.0`.
5. Generate a public domain under **Settings → Networking**.

No `.env` file is needed on Railway—use project variables only.

Health check: `GET /api/health`

## GitHub

```bash
git init
git add .
git commit -m "Initial commit: Sementic Analysis Tool v0.00001"
git branch -M main
git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git
git push -u origin main
```

## Documentation

- [docs/FLOW.md](docs/FLOW.md) — end-to-end pipeline (input → AI → matrices → graphs)  
- [docs/METHODS.md](docs/METHODS.md) — how each analysis is computed  
- [docs/PROMPTS.md](docs/PROMPTS.md) — OpenAI system/user prompts  
- [docs/PLACES.md](docs/PLACES.md) — Google Maps place picker & reviews  

## Project layout

| Path | Role |
|------|------|
| `app.py` | FastAPI server |
| `ai_preprocess.py` | Translate to English + OpenAI concept extraction |
| `analyses.py` | Matrix computation |
| `graph.py` | Matrix → network graph |
| `ai_relations.py` | AI direction & polarity on graph links |
| `google_places.py` | Google Places review fetch |
| `analysis_service.py` | Shared Sementic pipeline (`/api/analyze` + review batch) |
| `static/` | Frontend |

## CLI (no AI, local tokenization only)

```bash
python main.py -i your_text.txt -o output --min-freq 0
```

Generated `output/` and `*.csv` / `*.xlsx` files are gitignored.
