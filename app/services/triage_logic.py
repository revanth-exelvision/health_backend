"""Deterministic triage helpers: KB load, symptom log merge, condition ranking."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from app.models.triage import (
    ConditionRankingResult,
    MergedSymptomLine,
    RankedCondition,
    TriageSymptomLog,
)
from app.services.text_match import kb_labels_match_patient_lines
from orchestrator.logging_setup import get_logger

logger = get_logger(__name__)

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"
_TRIAGE_FILE = "medical_conditions_triage.json"
_SIMPLIFIED_FILE = "medical_conditions_simplified.json"

# Max fraction of (sum of symptom weights) applied as extra score from matched risks.
_RISK_BONUS_CAP_FRACTION = 0.3


def knowledge_path() -> Path:
    """Path to the primary KB JSON for transcript symptom cataloging.

    Prefers :file:`medical_conditions_triage.json`; falls back to simplified when triage is absent.
    Ranking always uses :func:`load_conditions_kb` (triage file only).
    """
    triage = _KNOWLEDGE_DIR / _TRIAGE_FILE
    if triage.is_file():
        return triage
    return _KNOWLEDGE_DIR / _SIMPLIFIED_FILE


def load_conditions_kb() -> list[dict[str, Any]]:
    """Load triage conditions from :file:`medical_conditions_triage.json` (symptoms, risks, ICD).

    Used by :func:`rank_conditions_for_log`, follow-up planning, and any tool that needs the full
    obstetric triage KB. Does not fall back to the simplified file.
    """
    path = _KNOWLEDGE_DIR / _TRIAGE_FILE
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("conditions", []))


def _icd10_match_labels(icd_list: Any) -> list[str]:
    """Short/long ICD descriptions from triage JSON ``icd10_cm`` entries for text overlap."""
    labels: list[str] = []
    if not isinstance(icd_list, list):
        return labels
    for icd in icd_list:
        if not isinstance(icd, dict):
            continue
        for key in ("short_description", "long_description"):
            t = str(icd.get(key) or "").strip()
            if t:
                labels.append(t)
    return labels


def _merge_symptom_match_labels(symptom_row: dict[str, Any]) -> list[str]:
    """Descriptions plus ICD text from ``medical_conditions_triage.json`` symptom rows."""
    descs = [str(d) for d in (symptom_row.get("descriptions") or []) if d]
    for t in _icd10_match_labels(symptom_row.get("icd10_cm")):
        if t not in descs:
            descs.append(t)
    return descs


def _merge_risk_match_labels(risk_row: dict[str, Any], rk_name: str) -> list[str]:
    """Triage JSON risk descriptions + ICD + consolidated patient_risk_signals cues."""
    from app.services.risk_signals import merged_history_cues_for_risk_name

    descs = [str(d) for d in (risk_row.get("descriptions") or []) if d]
    for t in _icd10_match_labels(risk_row.get("icd10_cm")):
        if t not in descs:
            descs.append(t)
    for c in merged_history_cues_for_risk_name(rk_name):
        if c not in descs:
            descs.append(c)
    return descs


def _patient_match_lines(log: TriageSymptomLog) -> list[tuple[str, bool]]:
    lines: list[tuple[str, bool]] = []
    for s in log.symptoms:
        lines.append((s.name, s.negated))
    if log.chief_complaint.strip():
        lines.append((log.chief_complaint.strip(), False))
    for p in log.negated_symptom_phrases:
        if p.strip():
            lines.append((p.strip(), True))
    for b in log.unstructured_bullets:
        if b.strip():
            lines.append((b.strip(), False))
    blob = " ".join(
        [log.vitals_summary, log.tests_summary, log.free_text_other]
    ).strip()
    if blob:
        lines.append((blob, False))
    return lines


def rank_conditions_for_log(log: TriageSymptomLog, top_k: int = 5) -> ConditionRankingResult:
    conditions = load_conditions_kb()
    patient_lines = _patient_match_lines(log)
    ranked: list[RankedCondition] = []

    for cond in conditions:
        cname = str(cond.get("name", ""))
        symptoms = cond.get("symptoms") or []
        symptom_score = 0.0
        matched: list[str] = []
        required_names = [
            str(s.get("name", ""))
            for s in symptoms
            if s.get("required") is True and s.get("name")
        ]

        symptom_weight_sum = 0.0
        for ks in symptoms:
            if not isinstance(ks, dict):
                continue
            ks_name = str(ks.get("name", ""))
            if not ks_name:
                continue
            weight = float(ks.get("weight") or 0.0)
            symptom_weight_sum += weight
            descs = _merge_symptom_match_labels(ks)
            ok, is_neg = kb_labels_match_patient_lines(ks_name, descs, patient_lines)
            if ok:
                if is_neg:
                    symptom_score -= 0.35 * weight
                else:
                    symptom_score += weight
                    matched.append(ks_name)

        risk_cap = _RISK_BONUS_CAP_FRACTION * symptom_weight_sum
        risk_raw = 0.0
        matched_risks: list[str] = []
        for rk in cond.get("risks") or []:
            if not isinstance(rk, dict):
                continue
            rk_name = str(rk.get("name", ""))
            if not rk_name:
                continue
            weight = float(rk.get("weight") or 0.0)
            descs = _merge_risk_match_labels(rk, rk_name)
            ok, is_neg = kb_labels_match_patient_lines(rk_name, descs, patient_lines)
            if ok and not is_neg:
                risk_raw += weight
                matched_risks.append(rk_name)

        risk_bonus = min(risk_raw, risk_cap) if risk_cap > 0 else 0.0
        score = symptom_score + risk_bonus

        missing_req = [r for r in required_names if r not in matched]
        ranked.append(
            RankedCondition(
                condition=cname,
                score=round(score, 4),
                matched_symptoms=list(dict.fromkeys(matched)),
                matched_risks=list(dict.fromkeys(matched_risks)),
                missing_required=missing_req,
            )
        )

    ranked.sort(key=lambda x: x.score, reverse=True)
    if top_k > 0:
        ranked = ranked[:top_k]
    return ConditionRankingResult(ranked=ranked)


def _vitals_summary(v: Any) -> str:
    if not v or not isinstance(v, dict):
        return ""
    parts = [f"{k}: {v}" for k, v in v.items() if v]
    return "; ".join(parts)


def _tests_summary(tests: Any) -> str:
    if not tests or not isinstance(tests, list):
        return ""
    parts: list[str] = []
    for t in tests:
        if isinstance(t, dict):
            n = t.get("name", "")
            val = t.get("value_text", "")
            parts.append(f"{n}={val}".strip())
    return "; ".join(p for p in parts if p)


def _merge_symptom_dicts(analyses: list[dict[str, Any]]) -> TriageSymptomLog:
    by_name: dict[str, MergedSymptomLine] = {}
    chief_parts: list[str] = []
    neg_phrases: list[str] = []
    bullets: list[str] = []
    free_parts: list[str] = []
    vitals_parts: list[str] = []
    tests_parts: list[str] = []
    notes: list[str] = []

    for i, raw in enumerate(analyses):
        if not isinstance(raw, dict):
            continue
        notes.append(f"analysis[{i}]")
        cc = str(raw.get("chief_complaint") or "").strip()
        if cc:
            chief_parts.append(cc)
        for p in raw.get("negated_symptom_phrases") or []:
            if isinstance(p, str) and p.strip():
                neg_phrases.append(p.strip())
        for b in raw.get("unstructured_bullets") or []:
            if isinstance(b, str) and b.strip():
                bullets.append(b.strip())
        ft = str(raw.get("free_text_other") or "").strip()
        if ft:
            free_parts.append(ft)
        vs = _vitals_summary(raw.get("vitals"))
        if vs:
            vitals_parts.append(vs)
        ts = _tests_summary(raw.get("test_results"))
        if ts:
            tests_parts.append(ts)

        for s in raw.get("symptoms") or []:
            if not isinstance(s, dict):
                continue
            name = str(s.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            neg = bool(s.get("negated"))
            present = s.get("present", True)
            if key not in by_name:
                by_name[key] = MergedSymptomLine(
                    name=name, present=bool(present), negated=neg
                )
            else:
                cur = by_name[key]
                by_name[key] = MergedSymptomLine(
                    name=cur.name,
                    present=cur.present and bool(present),
                    negated=cur.negated or neg,
                )

    return TriageSymptomLog(
        rchid=None,
        symptoms=list(by_name.values()),
        chief_complaint="; ".join(dict.fromkeys(chief_parts)),
        negated_symptom_phrases=list(dict.fromkeys(neg_phrases)),
        vitals_summary=" | ".join(vitals_parts),
        tests_summary=" | ".join(tests_parts),
        unstructured_bullets=list(dict.fromkeys(bullets)),
        free_text_other=" | ".join(dict.fromkeys(free_parts)),
        source_notes=notes,
    )


def fetch_symptom_analyses_for_rchid(rchid: str, limit: int = 20) -> list[dict[str, Any]]:
    """Load structured_output_json payloads from derived symptom log for an rchid."""
    from app.tools.csv_tools import medical_data_root

    root = medical_data_root()
    path = root / "derived" / "symptom_analysis_log.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
    matching = [r for r in rows if str(r.get("rchid", "")).strip() == rchid.strip()]
    matching.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for r in matching[:limit]:
        raw = r.get("structured_output_json") or ""
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            logger.warning(
                "fetch_symptom_analyses_for_rchid: skipping row with invalid structured_output_json"
            )
            continue
    return out


def merge_symptom_log_payload(payload: dict[str, Any]) -> TriageSymptomLog:
    """Build TriageSymptomLog from transcript_analysis, logged_analyses, and/or rchid CSV rows."""
    analyses: list[dict[str, Any]] = []
    rchid = payload.get("rchid")
    rchid_s = str(rchid).strip() if rchid is not None else ""

    ta = payload.get("transcript_analysis")
    if isinstance(ta, dict):
        analyses.append(ta)

    logged = payload.get("logged_analyses")
    if isinstance(logged, list):
        for item in logged:
            if isinstance(item, dict):
                analyses.append(item)

    if rchid_s and payload.get("include_csv_log", True) is not False:
        analyses.extend(fetch_symptom_analyses_for_rchid(rchid_s))

    if not analyses:
        log = TriageSymptomLog(
            rchid=rchid_s or None,
            source_notes=["no transcript or log data provided"],
        )
        return log

    merged = _merge_symptom_dicts(analyses)
    merged.rchid = rchid_s or None
    merged.source_notes = [
        f"merged {len(analyses)} analysis record(s)",
        *merged.source_notes,
    ]
    return merged


def active_clinical_from_history_analyses(
    analyses: list[dict[str, Any]],
    *,
    rchid: str | None = None,
    conditions_top_k: int = 10,
) -> tuple[list[str], list[tuple[str, float]]]:
    """Present (non-negated) symptom names and triage KB conditions with score > 0 from merged history."""
    if not analyses:
        return [], []
    merged = _merge_symptom_dicts([a for a in analyses if isinstance(a, dict)])
    merged.rchid = rchid
    active_syms = list(
        dict.fromkeys(s.name for s in merged.symptoms if s.present and not s.negated)
    )
    try:
        tk = int(conditions_top_k)
    except (TypeError, ValueError):
        tk = 10
    tk = max(1, min(tk, 100))
    ranked = rank_conditions_for_log(merged, top_k=tk)
    active_conds = [(r.condition, r.score) for r in ranked.ranked if r.score > 0.0]
    return active_syms, active_conds


def _format_icd_line(prefix: str, icd: dict[str, Any]) -> str:
    code = icd.get("code", "")
    short_d = icd.get("short_description", "")
    long_d = icd.get("long_description", "")
    role = icd.get("role", "")
    if long_d and long_d != short_d:
        return f"  {prefix} {code} ({role}): {short_d} — {long_d}"
    return f"  {prefix} {code} ({role}): {short_d}"


def format_kb_condition_block(cond: dict[str, Any]) -> str:
    """Human-readable symptom, risk, and ICD list for LLM prompts."""
    lines = [f"Condition: {cond.get('name', '')}"]
    for icd in cond.get("icd10_cm") or []:
        if isinstance(icd, dict):
            lines.append(_format_icd_line("ICD-10-CM", icd))
    lines.append("Symptoms:")
    for s in cond.get("symptoms") or []:
        nm = s.get("name", "")
        w = s.get("weight", "")
        req = s.get("required", False)
        descs = s.get("descriptions") or []
        lines.append(
            f"  - {nm} (weight={w}, required={req})"
            + (f" examples: {', '.join(descs)}" if descs else "")
        )
        for icd in s.get("icd10_cm") or []:
            if isinstance(icd, dict):
                lines.append(_format_icd_line("    ICD", icd))
    risks = cond.get("risks") or []
    if risks:
        lines.append("Risk factors (lower weight in scoring; cap applies):")
        for r in risks:
            if not isinstance(r, dict):
                continue
            nm = r.get("name", "")
            w = r.get("weight", "")
            descs = r.get("descriptions") or []
            lines.append(
                f"  - {nm} (weight={w})"
                + (f" examples: {', '.join(descs)}" if descs else "")
            )
            for icd in r.get("icd10_cm") or []:
                if isinstance(icd, dict):
                    lines.append(_format_icd_line("    ICD", icd))
    return "\n".join(lines)
