# Health backend

FastAPI orchestrator service for obstetric triage and transcript analysis, plus an optional Streamlit chat client that calls the HTTP API.

## Prerequisites

- Python 3.11+ (as used in development)
- A virtual environment
- Dependencies: `orchestrator` (LangGraph / LangChain stack), `fastapi`, `uvicorn`, and the packages your tools require (for example `langchain-openai` if you use OpenAI). Install whatever your environment already uses for this repo, then install the chat UI dependencies below.

### Environment variables

- **`OPENAI_API_KEY`** — Required for LLM calls (orchestrator uses `pydantic-settings`; see `orchestrator` package `Settings`).
- **`OPENAI_MODEL`** — Optional; defaults to `gpt-4o-mini` if unset.
- **`MEDICAL_DATA_DIR`** — Optional. If set, CSV tools read/write under this directory instead of `app/data/medical_data`.

You can place values in a `.env` file at the project root (loaded by the orchestrator settings).

### Chat UI dependencies

```bash
pip install -r chat/requirements.txt
```

This pulls in Streamlit and `httpx` for the API client.

## Run from the project root

Commands below assume the current working directory is the repository root (so the `app` package imports correctly).

### API server (FastAPI)

```bash
uvicorn app.app:app --host 0.0.0.0 --port 8000
```

- Interactive docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health check: `GET /health` → `{"status":"ok"}`

Useful orchestration routes:

| Method | Path | Purpose |
|--------|------|--------|
| `POST` | `/orchestrate/json` | Plan + execute in one request |
| `POST` | `/orchestrate/flows/{flow_id}` | Run a named flow (for example `triage_session`, `analyze_transcript`) |
| `GET` | `/orchestrate/flows` | List available flows |
| `GET` | `/orchestrate/tools` | List registered tools |

### Streamlit chat client

With the API running (default base URL `http://127.0.0.1:8000`):

```bash
streamlit run chat/app.py
```

Open the URL shown in the terminal (typically [http://localhost:8501](http://localhost:8501)). In the sidebar you can change the API base URL, choose named flow vs full orchestration, and optionally pass JSON context (for example `rchid`).

### Tests

```bash
python -m unittest discover -s tests -v
```

Or a single module:

```bash
python -m unittest tests.test_triage_ranking -v
```

## Project layout (high level)

- `app/` — Application package: `app.py` (FastAPI app), `tools/`, `services/`, `models/`, `data/`
- `chat/` — Streamlit UI and small HTTP client for the orchestrator API
- `tests/` — Unit tests
