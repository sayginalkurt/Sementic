# Sementic Analysis Tool

Thematic concept extraction (OpenAI) with two parallel pipelines:

- **STAT-3NET** — co-occurrence, semantic, and epistemic (ENA-style) matrices + directed graphs
- **FCM** — hybrid NLP phrase extraction, embedding clusters, LLM concept merge, causal fuzzy cognitive map (adjacency matrix + evidence edges)

Web UI with workflow trace, matrices, interactive graphs (PNG export), and XLSX export.

**Version:** v0.00001

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
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
| `APP_PASSWORD` | App login password (Railway only; no gate when running locally) |

4. spaCy English model (`en_core_web_sm`) is installed automatically via `requirements.txt` + Nixpacks build.
5. Railway sets `PORT` automatically; the app binds to `0.0.0.0`.
6. Generate a public domain under **Settings → Networking**.

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
| `analysis_service.py` | STAT-3NET pipeline (`pipeline=statistical`) |
| `fcm_service.py` | FCM pipeline (`pipeline=fcm`) |
| `concept_hybrid.py` | spaCy phrases + embeddings + LLM concept merge |
| `fcm_inference.py` | Contextual polarity + causal FCM edges |
| `lang_detect.py` | Language detection; skip translation for English |
| `static/` | Frontend |

## CLI (no AI, local tokenization only)

```bash
python main.py -i your_text.txt -o output --min-freq 0
```

Generated `output/` and `*.csv` / `*.xlsx` files are gitignored.
