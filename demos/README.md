# Flow demos

Examples for the named orchestrator flows in [`app/app.py`](../app/app.py):

| Flow ID | Purpose |
|--------|---------|
| `triage_session` | Patient-aware triage: use `context.patient_state` and/or load via `get_patient_state`, then merge/rank/plan/consolidate |
| `analyze_transcript` | Transcript extraction with the same patient-state input (preloaded or loaded with `get_patient_state`) |
| `patient_info_risk` | Load `PatientState` (metadata, history, risks, optional active symptoms/conditions) |

**Request `context`:** clients may send `rchid`, registration-style identifiers, and optionally **`patient_state`** (full `PatientState` JSON). If `patient_state` is omitted, flows instruct the agent to call `get_patient_state` when identifiers allow.

## Prerequisites

1. **API** — from repo root:

   ```bash
   uvicorn app.app:app --host 127.0.0.1 --port 8000
   ```

2. **LLM** — flows call tools via the orchestrator agent; configure server env (e.g. `OPENAI_API_KEY`, model via orchestrator settings).

3. **Optional data** — for registration/symptom CSV lookups, set `MEDICAL_DATA_DIR` to your [`app/data/medical_data`](../app/data/medical_data) tree (or a copy with `mother/mother registration.csv`, `derived/symptom_analysis_log.csv`).

## Python runner (stdlib only)

```bash
# Default base URL http://127.0.0.1:8000
python demos/demo_flows.py triage
python demos/demo_flows.py transcript
python demos/demo_flows.py patient_info

# Or all three in sequence
python demos/demo_flows.py all

# Custom server
ORCHESTRATOR_BASE_URL=http://127.0.0.1:8000 python demos/demo_flows.py triage
```

## curl

```bash
chmod +x demos/curl_*.sh
./demos/curl_triage_session.sh
./demos/curl_analyze_transcript.sh
./demos/curl_patient_info_risk.sh
```

Override base URL:

```bash
ORCHESTRATOR_BASE_URL=http://127.0.0.1:8000 ./demos/curl_triage_session.sh
```

## Responses

Named flows return JSON with an **`answer`** field (natural-language summary from the agent). Tool JSON (triage consolidation, `PatientState`, etc.) is produced inside the run; see server logs or extend the API if you need structured traces in HTTP responses.
