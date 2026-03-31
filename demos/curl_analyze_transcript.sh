#!/usr/bin/env bash
set -euo pipefail
BASE="${ORCHESTRATOR_BASE_URL:-http://127.0.0.1:8000}"
curl -sS -X POST "${BASE}/orchestrate/flows/analyze_transcript" \
  -H "Content-Type: application/json" \
  -d "$(python3 <<'PY'
import json

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
    "user_prompt": """Analyze this transcript (structured summary only; do not log to CSV unless asked).
Use patient state from context (or get_patient_state) when interpreting findings.

Nurse: Main concern?
Patient: Burning with urination and frequency since yesterday. No fever.
Nurse: Medications?
Patient: Just prenatal vitamins.
""",
    "chat_history": [],
    "model": None,
    "context": ctx,
    "metadata": None,
}))
PY
)" | python3 -m json.tool
