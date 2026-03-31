#!/usr/bin/env python3
"""Demonstrate named orchestrator flows (triage_session, analyze_transcript, patient_info_risk).

Requires a running API (uvicorn app.app:app) and LLM credentials on the server.
Uses only the Python standard library (no httpx).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = os.environ.get("ORCHESTRATOR_BASE_URL", "http://127.0.0.1:8000")

# Shared demo identifiers — optional preloaded patient_state (gateway may pass full PatientState JSON).
DEMO_RCHID = "RCHID00000001"


def _demo_context_preload_patient_state() -> dict:
    """Minimal PatientState-shaped object for clients that inject state before the agent runs."""
    return {
        "rchid": DEMO_RCHID,
        "patient_state": {
            "metadata": {"rchid": DEMO_RCHID, "registration": {}},
            "history": {"analyses": [], "count": 0},
            "identified_risks": [],
            "active_symptoms": [],
            "active_conditions": [],
            "search_text_preview": None,
        },
    }


def post_flow(base: str, flow_id: str, payload: dict) -> dict:
    url = f"{base.rstrip('/')}/orchestrate/flows/{flow_id}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        body = r.read().decode("utf-8")
    return json.loads(body)


def health(base: str) -> dict:
    url = f"{base.rstrip('/')}/health"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def demo_triage(base: str) -> dict:
    payload = {
        "user_prompt": (
            "Run obstetric triage for this visit. Patient says: severe headache for two days, "
            "vision is blurry with sparkles, some swelling in ankles. "
            "They deny chest pain. Use patient state from context (or load via get_patient_state) "
            "then run the merge/rank/plan/consolidate steps."
        ),
        "chat_history": [],
        "model": None,
        "context": _demo_context_preload_patient_state(),
        "metadata": None,
    }
    return post_flow(base, "triage_session", payload)


def demo_transcript(base: str) -> dict:
    transcript = """
Nurse: What brings you in today?
Patient: I've been having burning when I pee and going way more often. No fever.
Nurse: Any allergies?
Patient: Penicillin — I get a rash.
Blood pressure 118/72, temp 98.2 oral.
""".strip()
    payload = {
        "user_prompt": (
            "Analyze this transcript; use patient state from context (or get_patient_state) "
            "so the summary can reference prior history/risks. "
            "Do not log to CSV unless I explicitly ask to save.\n\n"
            f"{transcript}"
        ),
        "chat_history": [],
        "model": None,
        "context": _demo_context_preload_patient_state(),
        "metadata": None,
    }
    return post_flow(base, "analyze_transcript", payload)


def demo_patient_info(base: str) -> dict:
    payload = {
        "user_prompt": (
            "Call get_patient_state with rchid from context. "
            "Summarize metadata, history count, identified_risks, and any active_symptoms / "
            "active_conditions from the tool JSON. Decision-support only; do not diagnose."
        ),
        "chat_history": [],
        "model": None,
        "context": {"rchid": DEMO_RCHID},
        "metadata": None,
    }
    return post_flow(base, "patient_info_risk", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run named orchestrator flow demos")
    parser.add_argument(
        "flow",
        choices=("triage", "transcript", "patient_info", "all"),
        help="Which demo to run",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE,
        help=f"Orchestrator base URL (default env ORCHESTRATOR_BASE_URL or {DEFAULT_BASE})",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    try:
        h = health(base)
        print(f"GET /health -> {h}\n")
    except urllib.error.URLError as e:
        print(f"Server not reachable at {base}: {e}", file=sys.stderr)
        print("Start the API: uvicorn app.app:app --host 127.0.0.1 --port 8000", file=sys.stderr)
        return 1

    runners = {
        "triage": ("triage_session", demo_triage),
        "transcript": ("analyze_transcript", demo_transcript),
        "patient_info": ("patient_info_risk", demo_patient_info),
    }

    order = ["triage", "transcript", "patient_info"] if args.flow == "all" else [args.flow]

    for key in order:
        flow_id, fn = runners[key]
        print("=" * 72)
        print(f"Flow: {flow_id}")
        print("=" * 72)
        try:
            out = fn(base)
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}", file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"Request failed: {e}", file=sys.stderr)
            return 1
        answer = out.get("answer", "")
        print(answer if isinstance(answer, str) else json.dumps(out, indent=2, ensure_ascii=False))
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
