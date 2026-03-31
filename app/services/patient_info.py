"""Pluggable patient info loading (CSV today; swap for HTTP/DB later)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.services.triage_logic import fetch_symptom_analyses_for_rchid

MOTHER_REGISTRATION_CSV = "mother/mother registration.csv"


@runtime_checkable
class PatientInfoSource(Protocol):
    """Resolve patient identifiers and load registration + symptom history."""

    def resolve_rchid(self, identifiers: dict[str, str]) -> str | None:
        """Return rchid from identifiers (e.g. explicit rchid) or first exact CSV match."""
        ...

    def get_registration(self, rchid: str) -> dict[str, str] | None:
        """Single mother registration row for rchid, or None."""
        ...

    def get_symptom_analyses(self, rchid: str, limit: int = 20) -> list[dict[str, Any]]:
        """Structured transcript analyses from derived log, newest first."""
        ...


def _mother_rows_with_filters(filters: dict[str, str]) -> list[dict[str, str]]:
    from app.tools.csv_tools import _read_csv_dicts, _resolve_safe_csv_path

    path = _resolve_safe_csv_path(MOTHER_REGISTRATION_CSV)
    _, rows = _read_csv_dicts(path)
    if not filters:
        return rows
    matched: list[dict[str, str]] = []
    for row in rows:
        ok = True
        for k, v in filters.items():
            if str(row.get(k, "")).strip() != str(v).strip():
                ok = False
                break
        if ok:
            matched.append(row)
    return matched


class CsvPatientInfoSource:
    """CSV-backed patient info (mother registration + derived symptom log)."""

    def resolve_rchid(self, identifiers: dict[str, str]) -> str | None:
        if not identifiers:
            return None
        r = str(identifiers.get("rchid", "")).strip()
        if r:
            return r
        filters = {k: str(v) for k, v in identifiers.items() if str(v).strip()}
        if not filters:
            return None
        rows = _mother_rows_with_filters(filters)
        if not rows:
            return None
        found = str(rows[0].get("rchid", "")).strip()
        return found or None

    def get_registration(self, rchid: str) -> dict[str, str] | None:
        r = str(rchid).strip()
        if not r:
            return None
        rows = _mother_rows_with_filters({"rchid": r})
        if not rows:
            return None
        return dict(rows[0])

    def get_symptom_analyses(self, rchid: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            lim = int(limit)
        except (TypeError, ValueError):
            lim = 20
        lim = max(1, min(lim, 100))
        return fetch_symptom_analyses_for_rchid(str(rchid).strip(), limit=lim)


def get_patient_info_source() -> PatientInfoSource:
    """Default factory; extend with env-based selection when adding HTTP backends."""
    return CsvPatientInfoSource()
