"""LangChain tools for reading and writing CSV files under app/data/medical_data.

Interim storage only; concurrent writes are best-effort. Not for production PHI without auth.

Derived CSV schema (optional logging for transcript analysis):
  ``derived/symptom_analysis_log.csv`` — columns:
  ``analysis_id`` (uuid), ``created_at`` (ISO-8601), ``rchid`` (optional mother id),
  ``structured_output_json`` (JSON string from ``analyze_transcript_symptoms``).
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from langchain.tools import tool

# Max rows returned by query_csv_rows to keep tool output bounded.
_MAX_QUERY_ROWS = 500


def medical_data_root() -> Path:
    env = os.environ.get("MEDICAL_DATA_DIR")
    if env:
        return Path(env).resolve()
    return (Path(__file__).resolve().parent.parent / "data" / "medical_data").resolve()


def _resolve_safe_csv_path(relative_path: str) -> Path:
    if not relative_path or not str(relative_path).strip():
        raise ValueError("relative_path is required")
    base = medical_data_root()
    rel = Path(relative_path)
    if rel.is_absolute():
        raise ValueError("absolute paths are not allowed")
    candidate = (base / rel).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as e:
        raise ValueError("path escapes medical data directory") from e
    if candidate.suffix.lower() != ".csv":
        raise ValueError("only .csv files are allowed")
    return candidate


def _read_csv_dicts(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV not found: {path}")
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def _write_csv_dicts(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _json_response(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


@tool
def query_csv_rows(relative_path: str, filters_json: str) -> str:
    """Query rows from a CSV under the medical data directory.

    Args:
        relative_path: Path relative to medical data root, e.g. "mother/mother registration.csv".
        filters_json: JSON object mapping column names to exact string values to match (AND).
            Use "{}" to return rows up to a cap (not all files — large files are truncated).

    Returns:
        JSON string: {"rows": [...], "truncated": bool, "matched_count": n}
    """
    try:
        path = _resolve_safe_csv_path(relative_path)
        filters = json.loads(filters_json) if filters_json.strip() else {}
        if not isinstance(filters, dict):
            return _json_response({"error": "filters_json must be a JSON object"})
        fieldnames, rows = _read_csv_dicts(path)
        if not filters:
            out = rows[:_MAX_QUERY_ROWS]
            return _json_response(
                {
                    "rows": out,
                    "truncated": len(rows) > _MAX_QUERY_ROWS,
                    "matched_count": len(rows),
                    "fieldnames": fieldnames,
                }
            )
        matched: list[dict[str, str]] = []
        for row in rows:
            ok = True
            for k, v in filters.items():
                if str(row.get(k, "")).strip() != str(v).strip():
                    ok = False
                    break
            if ok:
                matched.append(row)
        out = matched[:_MAX_QUERY_ROWS]
        return _json_response(
            {
                "rows": out,
                "truncated": len(matched) > _MAX_QUERY_ROWS,
                "matched_count": len(matched),
                "fieldnames": fieldnames,
            }
        )
    except Exception as e:
        return _json_response({"error": str(e)})


@tool
def append_csv_row(relative_path: str, row_json: str) -> str:
    """Append one row to a CSV. Keys must match existing headers; new files get headers from this row.

    Args:
        relative_path: Relative path under medical data, e.g. "derived/symptom_analysis_log.csv".
        row_json: JSON object of column -> value (strings).

    Returns:
        JSON string with ok status or error.
    """
    try:
        path = _resolve_safe_csv_path(relative_path)
        data = json.loads(row_json)
        if not isinstance(data, dict):
            return _json_response({"error": "row_json must be a JSON object"})
        str_data = {str(k): "" if v is None else str(v) for k, v in data.items()}
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            fieldnames = list(str_data.keys())
            _write_csv_dicts(path, fieldnames, [str_data])
            return _json_response({"ok": True, "appended": True, "created": True})
        fieldnames, _ = _read_csv_dicts(path)
        if not fieldnames:
            return _json_response({"error": "CSV has no header row"})
        unknown = set(str_data) - set(fieldnames)
        if unknown:
            return _json_response(
                {"error": f"keys not in CSV header: {sorted(unknown)}", "fieldnames": fieldnames}
            )
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writerow({k: str_data.get(k, "") for k in fieldnames})
        return _json_response({"ok": True, "appended": True, "created": False})
    except Exception as e:
        return _json_response({"error": str(e)})


@tool
def upsert_csv_row(
    relative_path: str, key_column: str, key_value: str, patch_json: str
) -> str:
    """Update the first row matching key_column == key_value, or append if none match.

    Args:
        relative_path: CSV path under medical data root.
        key_column: Column name used as the lookup key.
        key_value: Value to match (string comparison, stripped).
        patch_json: JSON object of columns to set (must be subset of header).

    Returns:
        JSON string describing updated, inserted, or error.
    """
    try:
        path = _resolve_safe_csv_path(relative_path)
        patch = json.loads(patch_json)
        if not isinstance(patch, dict):
            return _json_response({"error": "patch_json must be a JSON object"})
        patch_s = {str(k): "" if v is None else str(v) for k, v in patch.items()}
        fieldnames, rows = _read_csv_dicts(path)
        if key_column not in fieldnames:
            return _json_response({"error": f"key_column not in header: {key_column}"})
        unknown = set(patch_s) - set(fieldnames)
        if unknown:
            return _json_response({"error": f"patch keys not in header: {sorted(unknown)}"})
        key_norm = str(key_value).strip()
        idx = None
        for i, row in enumerate(rows):
            if str(row.get(key_column, "")).strip() == key_norm:
                idx = i
                break
        if idx is not None:
            merged = dict(rows[idx])
            for k, v in patch_s.items():
                merged[k] = v
            rows[idx] = {fn: merged.get(fn, "") for fn in fieldnames}
            _write_csv_dicts(path, fieldnames, rows)
            return _json_response({"ok": True, "action": "updated", "key_column": key_column})
        new_row = {fn: "" for fn in fieldnames}
        new_row[key_column] = str(key_value)
        for k, v in patch_s.items():
            new_row[k] = v
        rows.append(new_row)
        _write_csv_dicts(path, fieldnames, rows)
        return _json_response({"ok": True, "action": "inserted", "key_column": key_column})
    except Exception as e:
        return _json_response({"error": str(e)})


CSV_TOOLS = [query_csv_rows, append_csv_row, upsert_csv_row]
