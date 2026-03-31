#!/usr/bin/env bash
set -euo pipefail
BASE="${ORCHESTRATOR_BASE_URL:-http://127.0.0.1:8000}"
curl -sS -X POST "${BASE}/orchestrate/flows/triage_session" \
  -H "Content-Type: application/json" \
  -d "$(python3 <<'PY'
import json

# Gateway may pass full PatientState; demo uses a minimal preload + rchid.
ctx = {
    "rchid": "RCHID00000001",
    "patient_state": {
        "metadata": {"rchid": "RCHID00000001", "registration": {}},
        "history": {"analyses": [], "count": 0},
        "identified_risks": [],
        "active_symptoms": [],
        "active_conditions": [],
        "search_text_preview": None,
    },
}
print(json.dumps({
    "user_prompt": (
        "Obstetric triage: patient reports severe headache and vision changes, mild ankle swelling. "
        "Denies chest pain. Use patient state from context (or get_patient_state) then merge/rank/plan/consolidate."
    ),
    "chat_history": [],
    "model": None,
    "context": ctx,
    "metadata": None,
}))
PY
)" | python3 -m json.tool
