"""Patient risk signals KB load and deterministic matching (patient_risk_signals.json)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.patient_state import IdentifiedRisk
from app.services.text_match import texts_overlap
from app.services.triage_logic import _merge_symptom_dicts, _patient_match_lines

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "data" / "knowledge"
_RISK_SIGNALS_FILE = "patient_risk_signals.json"

_MAX_PREVIEW = 4000


def knowledge_dir() -> Path:
    return _KNOWLEDGE_DIR


def load_patient_risk_signals_kb() -> list[dict[str, Any]]:
    path = _KNOWLEDGE_DIR / _RISK_SIGNALS_FILE
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("risks") or [])


_CUES_BY_RISK_NAME_LOWER: dict[str, list[str]] | None = None


def merged_history_cues_for_risk_name(risk_name: str) -> list[str]:
    """Union of ``history_cues`` from ``patient_risk_signals.json`` for this risk label (case-insensitive).

    Used by triage ranking so condition risk scoring uses the same consolidated cues as ``get_patient_state``.
    """
    global _CUES_BY_RISK_NAME_LOWER
    if _CUES_BY_RISK_NAME_LOWER is None:
        idx: dict[str, list[str]] = {}
        for r in load_patient_risk_signals_kb():
            if not isinstance(r, dict):
                continue
            nm = str(r.get("name") or "").strip()
            if not nm:
                continue
            key = nm.lower()
            cues = [str(c).strip() for c in (r.get("history_cues") or []) if str(c).strip()]
            if key not in idx:
                idx[key] = []
            seen = set(idx[key])
            for c in cues:
                if c not in seen:
                    idx[key].append(c)
                    seen.add(c)
        _CUES_BY_RISK_NAME_LOWER = idx
    return list(_CUES_BY_RISK_NAME_LOWER.get(str(risk_name).strip().lower(), []))


def build_patient_match_lines(
    registration: dict[str, str],
    analyses: list[dict[str, Any]],
) -> list[tuple[str, bool]]:
    """Lines for overlap matching: registration values + merged symptom log (with negation)."""
    lines: list[tuple[str, bool]] = []
    for _k, v in registration.items():
        s = str(v).strip()
        if s:
            lines.append((s, False))
    merged = _merge_symptom_dicts(
        [a for a in analyses if isinstance(a, dict)]
    )
    lines.extend(_patient_match_lines(merged))
    return lines


def build_patient_search_text(
    registration: dict[str, str],
    analyses: list[dict[str, Any]],
) -> str:
    """Single searchable blob for previews and optional external use."""
    parts: list[str] = []
    for k, v in registration.items():
        s = str(v).strip()
        if s:
            parts.append(f"{k}: {s}")
    merged = _merge_symptom_dicts(
        [a for a in analyses if isinstance(a, dict)]
    )
    if merged.chief_complaint.strip():
        parts.append(merged.chief_complaint.strip())
    for s in merged.symptoms:
        parts.append(s.name)
    for p in merged.negated_symptom_phrases:
        if p.strip():
            parts.append(p.strip())
    for b in merged.unstructured_bullets:
        if b.strip():
            parts.append(b.strip())
    blob = " ".join(
        [merged.vitals_summary, merged.tests_summary, merged.free_text_other]
    ).strip()
    if blob:
        parts.append(blob)
    return " \n ".join(parts)


def match_patient_risk_signals(
    patient_lines: list[tuple[str, bool]],
    risks: list[dict[str, Any]] | None = None,
) -> list[IdentifiedRisk]:
    """Match KB risks to patient lines; only non-negated overlaps count (aligned with triage risk scoring)."""
    rows = risks if risks is not None else load_patient_risk_signals_kb()
    out: list[IdentifiedRisk] = []

    for r in rows:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "").strip()
        rid = str(r.get("id") or "").strip()
        cues = [str(c).strip() for c in (r.get("history_cues") or []) if str(c).strip()]
        conds = [str(c).strip() for c in (r.get("conditions") or []) if str(c).strip()]
        labels: list[str] = []
        if name:
            labels.append(name)
        for c in cues:
            if c not in labels:
                labels.append(c)
        if not labels:
            continue

        matched_cues: list[str] = []
        for label in labels:
            for pt, is_neg in patient_lines:
                if texts_overlap(pt, label) and not is_neg:
                    matched_cues.append(label)
                    break
        matched_cues = list(dict.fromkeys(matched_cues))
        if not matched_cues:
            continue
        out.append(
            IdentifiedRisk(
                id=rid,
                name=name or labels[0],
                matched_cues=matched_cues,
                conditions=conds,
            )
        )
    return out


def search_text_preview(text: str, max_len: int = _MAX_PREVIEW) -> str | None:
    if not text.strip():
        return None
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"
