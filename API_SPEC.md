# Health backend — HTTP API specification

This document describes the **orchestrator REST API** served by this repo.

**Run locally (from repo root):**

```bash
uvicorn app.app:app --host 0.0.0.0 --port 8000
```

Implementation: [`app/app.py`](app/app.py) uses `orchestrator.main.create_app`. For a machine-readable schema, start the server and open **`GET /openapi.json`** or **`GET /docs`**.

---

## Overview

| Item | Value |
|------|--------|
| Title / version | Orchestrator `0.1.0` (from installed `orchestrator` package) |
| Default base URL | `http://127.0.0.1:8000` |
| OpenAPI JSON | `GET /openapi.json` |
| Swagger UI | `GET /docs` |
| ReDoc | `GET /redoc` |
| HTTP authentication | None |
| LLM | Server-side env (e.g. `OPENAI_API_KEY`, `OPENAI_MODEL` via `orchestrator` settings / `.env`) |

**Registered tools:** [`HEALTH_TOOLS`](app/tools/__init__.py) only (CSV, transcript, triage helpers, etc.).

**Registered flows:** [`my_flows`](app/app.py) only — `triage_session`, `analyze_transcript`, `patient_info_risk` (no merge with default demo flows unless you change `create_app`).

---

## Shared schemas

Schemas match `orchestrator.models` (Pydantic).

### `ChatMessageItem`

```json
{
  "role": "user | assistant | system",
  "content": "string"
}
```

### `OrchestratePayload`

Used by: `POST /orchestrate/json`, `POST /orchestrate`, `POST /orchestrate/plan`.

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `user_prompt` | string | yes | Current user turn |
| `chat_history` | `ChatMessageItem[]` | no | Default `[]` |
| `model` | string \| null | no | Override server default model |
| `context` | object \| null | no | Included in attachment/context for the agent |
| `metadata` | object \| null | no | Same |

### `PlanStep`

| Field | Type | Required |
|-------|------|----------|
| `step_id` | string | yes |
| `description` | string | yes |
| `tool_name` | string \| null | no |
| `inputs` | string | no (default `""`) |
| `expected_output` | string | no (default `""`) |

### `OrchestratorPlan`

| Field | Type |
|-------|------|
| `goal_summary` | string |
| `steps` | `PlanStep[]` |
| `final_output_description` | string |

### `OrchestrateResponse`

| Field | Type |
|-------|------|
| `plan` | `OrchestratorPlan` |
| `answer` | string |

### `NamedFlowExecutePayload`

Same fields as `OrchestratePayload` (used for named flows).

### `ExecutePayload`

Same as `OrchestratePayload` plus:

| Field | Type | Required |
|-------|------|----------|
| `plan` | `OrchestratorPlan` | yes |

### `ExecuteResponse`

| Field | Type |
|-------|------|
| `answer` | string |

### `ToolSummary`

| Field | Type |
|-------|------|
| `name` | string |
| `description` | string |

### `FlowSummary`

| Field | Type |
|-------|------|
| `flow_id` | string |
| `title` | string |
| `description` | string |

---

## Endpoints

### `GET /health`

**Response** `200` — `application/json`

```json
{ "status": "ok" }
```

---

### `GET /orchestrate/tools`

**Response** `200` — `application/json` — `ToolSummary[]`

---

### `GET /orchestrate/flows`

**Response** `200` — `application/json` — `FlowSummary[]`

---

### `POST /orchestrate/json`

**Content-Type:** `application/json`  
**Body:** `OrchestratePayload`

**Response** `200` — `OrchestrateResponse`

Runs planner → executor (no file uploads).

---

### `POST /orchestrate`

**Content-Type:** `multipart/form-data`

| Part | Type | Required |
|------|------|----------|
| `payload` | string (JSON) | yes — must validate as `OrchestratePayload` |
| `files` | file(s) | no |

**Response** `200` — `OrchestrateResponse`

**Error** `413` — body too large (`Content-Length` vs server `max_total_request_bytes`).

---

### `POST /orchestrate/plan`

**Body:** `OrchestratePayload`

**Response** `200` — `OrchestratorPlan`

Planner only; does not execute tools.

---

### `POST /orchestrate/execute`

**Body:** `ExecutePayload`

**Response** `200` — `ExecuteResponse`

Executor only. `plan.steps[*].tool_name` values must match tools registered on this server.

---

### `POST /orchestrate/flows/{flow_id}`

**Path:** `flow_id` — one of the server’s flow ids (this repo: `triage_session`, `analyze_transcript`, `patient_info_risk`).

**Body:** `NamedFlowExecutePayload`

**Response** `200` — `ExecuteResponse`

**Error** `404` — unknown `flow_id`.

The server loads a fixed `OrchestratorPlan` for that flow and runs the ReAct executor. Structured tool outputs (e.g. triage JSON) are embedded in the agent run; the HTTP response exposes **`answer`** as the final assistant text unless you extend the API to return tool traces.

---

## Example: triage named flow

`context` may include **`patient_state`** (full `PatientState` JSON from your gateway). If omitted, the flow plan instructs the agent to call `get_patient_state` when `rchid` or registration filters are available.

```http
POST /orchestrate/flows/triage_session
Content-Type: application/json

{
  "user_prompt": "Patient reports severe headache and vision changes. RCH ID RCHID00000001.",
  "chat_history": [],
  "model": null,
  "context": {
    "rchid": "RCHID00000001",
    "patient_state": {
      "metadata": { "rchid": "RCHID00000001", "registration": {} },
      "history": { "analyses": [], "count": 0 },
      "identified_risks": [],
      "active_symptoms": [],
      "active_conditions": [],
      "search_text_preview": null
    }
  },
  "metadata": null
}
```

**Response (shape):**

```json
{
  "answer": "… natural-language triage summary …"
}
```

---

## Example: transcript analysis flow

Same `context` conventions as triage: optional preloaded **`patient_state`**, else `rchid` / identifiers for `get_patient_state`.

```http
POST /orchestrate/flows/analyze_transcript
Content-Type: application/json

{
  "user_prompt": "<clinical transcript text>",
  "chat_history": [],
  "model": null,
  "context": { "rchid": "RCHID00000001", "patient_state": null },
  "metadata": null
}
```

Use a full `patient_state` object instead of `null` when the gateway already loaded it.

---

## Example: patient state + risk signals flow

```http
POST /orchestrate/flows/patient_info_risk
Content-Type: application/json

{
  "user_prompt": "Call get_patient_state and summarize PatientState (metadata, history, risks, active symptoms/conditions).",
  "chat_history": [],
  "model": null,
  "context": { "rchid": "RCHID00000001" },
  "metadata": null
}
```

Or resolve via registration filters (exact CSV columns), e.g. `"user_prompt": "Use identifiers_json {\"mobileno\": \"+91…\"} with get_patient_state."` with empty `context` if the agent passes JSON from the message.

---

## Runnable demos

See [`demos/README.md`](demos/README.md) — `python demos/demo_flows.py …` and `demos/curl_*.sh` examples.
