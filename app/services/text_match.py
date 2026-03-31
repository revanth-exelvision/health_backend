"""Shared text overlap helpers for KB matching (triage symptoms/risks, patient risk signals)."""

from __future__ import annotations

import re


def tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^\w]+", text.lower()) if len(t) > 1}


def texts_overlap(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return False
    return bool(ta & tb)


def kb_labels_match_patient_lines(
    primary: str,
    extra_labels: list[str],
    patient_lines: list[tuple[str, bool]],
) -> tuple[bool, bool]:
    """Returns (matched, negated) — negated True if the first overlap is on a negated patient line."""
    for pt, is_neg in patient_lines:
        if texts_overlap(pt, primary):
            return True, is_neg
        for d in extra_labels:
            if texts_overlap(pt, d):
                return True, is_neg
    return False, False
