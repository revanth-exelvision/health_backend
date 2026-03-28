"""
Streamlit chat UI for the health orchestrator API.

Run the API (from repo root):
  uvicorn app.app:app --host 0.0.0.0 --port 8000

Run this app (from repo root):
  streamlit run chat/app.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
import streamlit as st

from chat.api_client import OrchestratorClient


def _parse_optional_json(label: str, raw: str) -> dict | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as e:
        st.error(f"{label}: invalid JSON — {e}")
        st.stop()
    if not isinstance(out, dict):
        st.error(f"{label}: must be a JSON object")
        st.stop()
    return out


st.set_page_config(page_title="Health orchestrator chat", layout="wide")
st.title("Health orchestrator")

with st.sidebar:
    st.subheader("API")
    base_url = st.text_input(
        "Base URL",
        value=st.session_state.get("api_base", "http://127.0.0.1:8000"),
        help="Orchestrator FastAPI base URL (no trailing slash).",
    )
    st.session_state["api_base"] = base_url

    mode = st.radio(
        "Mode",
        ("Named flow", "Full orchestration"),
        help="Named flow uses a server-defined plan; full run plans + executes in one call.",
    )

    flow_id = "triage_session"
    client = OrchestratorClient(base_url)
    try:
        flows = client.list_flows()
        ids = [f["flow_id"] for f in flows]
        if mode == "Named flow":
            if ids:
                default_i = ids.index("triage_session") if "triage_session" in ids else 0
                flow_id = st.selectbox("Flow", ids, index=default_i)
            else:
                flow_id = st.text_input("Flow ID", value="triage_session")
    except Exception as e:
        st.warning(f"Could not list flows (is the API running?): {e}")
        if mode == "Named flow":
            flow_id = st.text_input("Flow ID", value="triage_session")

    model = st.text_input("Model (optional)", value="", help="Override LLM; leave empty for server default.")

    context_json = st.text_area(
        "Context JSON (optional)",
        value="",
        height=100,
        help='Merged into request context, e.g. {"rchid": "..."}',
    )

    if st.button("Check /health"):
        try:
            h = client.health()
            st.success(json.dumps(h))
        except Exception as e:
            st.error(str(e))

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prompt = st.chat_input("Message")
if prompt:
    context = _parse_optional_json("Context", context_json) if context_json.strip() else None
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]
    model_val = model.strip() or None

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Calling API…"):
            try:
                if mode == "Named flow":
                    data = client.named_flow(
                        flow_id,
                        user_prompt=prompt,
                        chat_history=history,
                        model=model_val,
                        context=context,
                    )
                    answer = data.get("answer", "")
                    st.markdown(answer)
                else:
                    data = client.orchestrate_json(
                        user_prompt=prompt,
                        chat_history=history,
                        model=model_val,
                        context=context,
                    )
                    answer = data.get("answer", "")
                    st.markdown(answer)
                    plan = data.get("plan")
                    if plan:
                        with st.expander("Plan (JSON)"):
                            st.json(plan)
            except httpx.HTTPStatusError as e:
                detail = e.response.text
                st.error(f"HTTP {e.response.status_code}: {detail}")
            except Exception as e:
                st.error(str(e))
            else:
                st.session_state.messages.append({"role": "user", "content": prompt})
                st.session_state.messages.append({"role": "assistant", "content": answer})
