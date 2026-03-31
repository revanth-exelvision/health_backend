#!/usr/bin/env bash
set -euo pipefail
BASE="${ORCHESTRATOR_BASE_URL:-http://127.0.0.1:8000}"
curl -sS -X POST "${BASE}/orchestrate/flows/patient_info_risk" \
  -H "Content-Type: application/json" \
  -d '{
    "user_prompt": "Call get_patient_state using rchid from context. Summarize PatientState: metadata, history count, identified_risks, active_symptoms, active_conditions. Decision-support only.",
    "chat_history": [],
    "model": null,
    "context": { "rchid": "RCHID00000001" },
    "metadata": null
  }' | python3 -m json.tool
