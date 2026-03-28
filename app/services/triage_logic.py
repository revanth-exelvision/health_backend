"""Deterministic triage helpers: KB load, symptom log merge, condition ranking."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from app.models.triage import (
    ConditionRankingResult,
    MergedSymptomLine,
    RankedCondition,
    TriageSymptomLog,
)


def knowledge_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "data"
        / "knowledge"
        / "medical_conditions_simplified.json"
    )


def load_conditions_kb() -> list[dict[str, Any]]:
    path = knowledge_path()
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("conditions", []))


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^\w]+", text.lower()) if len(t) > 1}


def _texts_overlap(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return False
    return bool(ta & tb)


def _kb_symptom_matches_patient(
    ks_name: str,
    descriptions: list[str],
    patient_lines: list[tuple[str, bool]],
) -> tuple[bool, bool]:
    """Returns (matched, negated) — negated True if match was on a negated patient line."""
    for pt, is_neg in patient_lines:
        if _texts_overlap(pt, ks_name):
            return True, is_neg
        for d in descriptions:
            if _texts_overlap(pt, d):
                return True, is_neg
    return False, False


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
        score = 0.0
        matched: list[str] = []
        required_names = [
            str(s.get("name", ""))
            for s in symptoms
            if s.get("required") is True and s.get("name")
        ]

        for ks in symptoms:
            ks_name = str(ks.get("name", ""))
            if not ks_name:
                continue
            weight = float(ks.get("weight") or 0.0)
            descs = [str(d) for d in (ks.get("descriptions") or []) if d]
            ok, is_neg = _kb_symptom_matches_patient(ks_name, descs, patient_lines)
            if ok:
                if is_neg:
                    score -= 0.35 * weight
                else:
                    score += weight
                    matched.append(ks_name)

        missing_req = [r for r in required_names if r not in matched]
        ranked.append(
            RankedCondition(
                condition=cname,
                score=round(score, 4),
                matched_symptoms=list(dict.fromkeys(matched)),
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


def format_kb_condition_block(cond: dict[str, Any]) -> str:
    """Human-readable symptom list for LLM prompts."""
    lines = [f"Condition: {cond.get('name', '')}"]
    for s in cond.get("symptoms") or []:
        nm = s.get("name", "")
        w = s.get("weight", "")
        req = s.get("required", False)
        descs = s.get("descriptions") or []
        lines.append(
            f"  - {nm} (weight={w}, required={req})"
            + (f" examples: {', '.join(descs)}" if descs else "")
        )
    return "\n".join(lines)
