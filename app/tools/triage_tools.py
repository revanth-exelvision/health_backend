"""LangChain tools for multi-step obstetric triage (merge log, rank, plan, consolidate)."""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.triage import (
    ConditionRankingResult,
    PerConditionPlansBundle,
    PerConditionTriagePlan,
    TriageConsolidation,
    TriageSymptomLog,
)
from app.services.triage_logic import (
    fetch_symptom_analyses_for_rchid,
    format_kb_condition_block,
    load_conditions_kb,
    merge_symptom_log_payload,
    rank_conditions_for_log,
)
from orchestrator.llm.factory import get_chat_model

_PLAN_SYSTEM = """You are a clinical decision-support assistant for obstetric triage. You are not a diagnosing physician.

The knowledge block below lists ONLY the symptoms defined for this single condition in the local knowledge base (names, weights, required flag, example phrases). Use it as the source of truth for what belongs to this condition.

Your tasks for THIS condition only:
1. questions — Short, actionable clarifying questions a nurse could ask next.
2. red_flags — KB-grounded symptoms/findings that, if present, STRONGLY support or would effectively confirm this condition for triage purposes. Prioritize symptoms with high weight and those marked required in the KB.
3. red_flags_present_in_log — Which of those red-flag items are already reflected in the patient log (explicitly or clearly implied).
4. red_flags_still_to_verify — Red-flag items not yet established in the log.
5. already_addressed — What is already reasonably clear from the log.
6. gaps — Important unknowns or missing information.

Rules:
- Do not claim a definitive diagnosis.
- Use cautious wording (e.g. "strongly supports", "should be verified by a clinician").
- Ground red_flags in the KB symptom list; you may rephrase slightly for clarity but keep clinical meaning aligned to those symptoms.
"""


_CONSOLIDATE_SYSTEM = """You consolidate several per-condition triage plans into one response for a nurse or decision-support UI.
You are not diagnosing.

Produce:
- questions — ONE flat list only. Merge and deduplicate overlapping questions; order by clinical urgency / usefulness. Do NOT group questions under condition headings. Do NOT prefix items with condition names (e.g. avoid "Preeclampsia: ..."). Each entry is a standalone question string.
- identified_conditions — Conditions where red flags are ALREADY present in the patient log such that this condition is strongly supported for triage (still not a formal diagnosis).
- potential_conditions — Conditions that remain plausible but are not yet established from the log.
- red_flags — ONE flat list only. Merge and deduplicate condition-confirming findings to verify or monitor. Do NOT group or label by condition; no subheadings or nested structure—only plain strings in a single array.
- rationale_brief — One short paragraph summarizing the triage picture; decision-support only.

Avoid duplicate entries across lists where possible."""


def _json_error(msg: str) -> str:
    return json.dumps({"error": msg}, ensure_ascii=False)


@tool
def lookup_mother_registration(identifiers_json: str) -> str:
    """Find mother row(s) in mother registration CSV to obtain rchid when not provided.

    Use when the user or context does not include rchid but supplies an exact phone, govrchid,
    member_id, name, or other column value as stored in ``mother/mother registration.csv``.
    Filters are ANDed with exact string match (trimmed).

    Args:
        identifiers_json: Non-empty JSON object, e.g. {"mobileno": "+919699370167"}
            or {"rchid": "RCHID00000001"}.

    Returns:
        JSON with rows, fieldnames, matched_count (same shape as query_csv_rows).
    """
    try:
        data = json.loads(identifiers_json) if identifiers_json.strip() else {}
        if not isinstance(data, dict) or not data:
            return _json_error("identifiers_json must be a non-empty JSON object")
        from app.tools.csv_tools import query_csv_rows

        return query_csv_rows.invoke(
            {
                "relative_path": "mother/mother registration.csv",
                "filters_json": json.dumps(data, ensure_ascii=False),
            }
        )
    except json.JSONDecodeError as e:
        return _json_error(f"invalid JSON: {e}")
    except Exception as e:
        return _json_error(str(e))


@tool
def fetch_patient_symptom_history(rchid: str, limit: int = 20) -> str:
    """Load prior structured symptom analyses from derived/symptom_analysis_log.csv for this mother.

    Use when triage needs patient history that was not included in the message: call this after you
    know rchid (from context or lookup_mother_registration), then pass ``analyses`` as
    ``logged_analyses`` into merge_symptom_log_for_triage (optionally with transcript_analysis).

    Args:
        rchid: Mother RCH identifier.
        limit: Max recent analyses to return, newest first (default 20, cap 100).

    Returns:
        JSON string: {"rchid", "count", "analyses": [ ... structured dicts ... ]}.
    """
    try:
        r = str(rchid).strip()
        if not r:
            return _json_error("rchid is required")
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            lim = 20
        lim = max(1, min(lim, 100))
        analyses = fetch_symptom_analyses_for_rchid(r, limit=lim)
        return json.dumps(
            {"rchid": r, "count": len(analyses), "analyses": analyses},
            ensure_ascii=False,
        )
    except Exception as e:
        return _json_error(str(e))


@tool
def merge_symptom_log_for_triage(payload_json: str) -> str:
    """Build a canonical symptom log for triage from transcript JSON and/or CSV history.

    Args:
        payload_json: JSON object with optional keys:
          - rchid: mother id — when set, appends recent rows from derived/symptom_analysis_log.csv
          - transcript_analysis: object (output shape of analyze_transcript_symptoms)
          - logged_analyses: list of those objects (e.g. from fetch_patient_symptom_history.analyses)
          - include_csv_log: optional bool, default true — set false to skip CSV when rchid is set

    If no transcript and no logged analyses are available but rchid is known, call
    fetch_patient_symptom_history first, or rely on include_csv_log true with rchid set.

    Returns:
        JSON string of TriageSymptomLog.
    """
    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            return _json_error("payload_json must be a JSON object")
        log = merge_symptom_log_payload(payload)
        return log.model_dump_json()
    except json.JSONDecodeError as e:
        return _json_error(f"invalid JSON: {e}")
    except Exception as e:
        return _json_error(str(e))


@tool
def rank_conditions_for_symptoms(canonical_symptom_log_json: str, top_k: int = 5) -> str:
    """Rank conditions from medical_conditions_simplified.json by overlap with the symptom log.

    Args:
        canonical_symptom_log_json: JSON string of TriageSymptomLog (from merge_symptom_log_for_triage).
        top_k: Maximum number of conditions to return (default 5).

    Returns:
        JSON string with key "ranked": list of {condition, score, matched_symptoms, missing_required}.
    """
    try:
        log = TriageSymptomLog.model_validate_json(canonical_symptom_log_json)
        try:
            k = int(top_k)
        except (TypeError, ValueError):
            k = 5
        if k < 1:
            k = 5
        result = rank_conditions_for_log(log, top_k=k)
        return result.model_dump_json()
    except Exception as e:
        return _json_error(str(e))


def _conditions_by_name() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in load_conditions_kb():
        n = str(c.get("name", "")).strip()
        if n:
            out[n] = c
    return out


@tool
def plan_followups_per_condition(
    canonical_symptom_log_json: str, ranked_conditions_json: str
) -> str:
    """For each top ranked condition, run an individual LLM evaluation (sequential internal calls).

    Args:
        canonical_symptom_log_json: TriageSymptomLog JSON.
        ranked_conditions_json: Output JSON from rank_conditions_for_symptoms (with "ranked" list).

    Returns:
        JSON with "per_condition": list of PerConditionTriagePlan objects.
    """
    try:
        log = TriageSymptomLog.model_validate_json(canonical_symptom_log_json)
        ranked_data = json.loads(ranked_conditions_json)
        if (
            isinstance(ranked_data, dict)
            and ranked_data.get("error") is not None
            and "ranked" not in ranked_data
        ):
            return ranked_conditions_json
        ranked = ConditionRankingResult.model_validate(ranked_data)
        by_name = _conditions_by_name()

        to_eval = [r for r in ranked.ranked if r.score > 0]
        if not to_eval:
            to_eval = ranked.ranked[: min(3, len(ranked.ranked))]

        llm = get_chat_model()
        structured = llm.with_structured_output(PerConditionTriagePlan)
        plans: list[PerConditionTriagePlan] = []
        log_text = json.dumps(log.model_dump(), indent=2, ensure_ascii=False)

        for row in to_eval:
            cname = row.condition
            cond = by_name.get(cname)
            if not cond:
                plans.append(
                    PerConditionTriagePlan(
                        condition_name=cname,
                        gaps=["Condition not found in local knowledge file"],
                    )
                )
                continue
            kb_block = format_kb_condition_block(cond)
            rank_blob = json.dumps(
                row.model_dump(), indent=2, ensure_ascii=False
            )
            human = (
                f"Patient / merged symptom log:\n{log_text}\n\n"
                f"Ranking row for this condition:\n{rank_blob}\n\n"
                f"Knowledge for this condition only:\n{kb_block}\n\n"
                f"Fill the structured plan for condition_name={cname!r} exactly."
            )
            msg = [
                SystemMessage(content=_PLAN_SYSTEM),
                HumanMessage(content=human),
            ]
            out: Any = structured.invoke(msg)
            if isinstance(out, PerConditionTriagePlan):
                if out.condition_name.strip().lower() != cname.strip().lower():
                    out = out.model_copy(update={"condition_name": cname})
                plans.append(out)
            elif isinstance(out, dict):
                plans.append(PerConditionTriagePlan.model_validate(out))
            else:
                plans.append(
                    PerConditionTriagePlan(
                        condition_name=cname,
                        gaps=["Model returned unexpected output"],
                    )
                )

        bundle = PerConditionPlansBundle(per_condition=plans)
        return bundle.model_dump_json()
    except json.JSONDecodeError as e:
        return _json_error(f"invalid JSON: {e}")
    except Exception as e:
        return _json_error(str(e))


@tool
def consolidate_triage_output(per_condition_plans_json: str) -> str:
    """Merge per-condition plans into flat lists of questions and red flags (not grouped by condition).

    Args:
        per_condition_plans_json: JSON from plan_followups_per_condition (PerConditionPlansBundle).

    Returns:
        JSON string of TriageConsolidation (questions and red_flags are each a single global list).
    """
    try:
        data = json.loads(per_condition_plans_json)
        if (
            isinstance(data, dict)
            and data.get("error") is not None
            and "per_condition" not in data
        ):
            return per_condition_plans_json
        bundle = PerConditionPlansBundle.model_validate(data)
        llm = get_chat_model()
        structured = llm.with_structured_output(TriageConsolidation)
        blob = json.dumps(
            [p.model_dump() for p in bundle.per_condition],
            indent=2,
            ensure_ascii=False,
        )
        human = (
            "Per-condition triage plans (JSON array):\n"
            f"{blob}\n\n"
            "Produce the consolidated triage output. "
            "The questions and red_flags fields must each be a single flat list with no per-condition grouping, "
            "headings, or condition-name prefixes on individual items."
        )
        msg = [SystemMessage(content=_CONSOLIDATE_SYSTEM), HumanMessage(content=human)]
        out: Any = structured.invoke(msg)
        if isinstance(out, TriageConsolidation):
            return out.model_dump_json()
        if isinstance(out, dict):
            return json.dumps(out, ensure_ascii=False)
        return _json_error("unexpected consolidation model output")
    except json.JSONDecodeError as e:
        return _json_error(f"invalid JSON: {e}")
    except Exception as e:
        return _json_error(str(e))


TRIAGE_TOOLS = [
    lookup_mother_registration,
    fetch_patient_symptom_history,
    merge_symptom_log_for_triage,
    rank_conditions_for_symptoms,
    plan_followups_per_condition,
    consolidate_triage_output,
]
