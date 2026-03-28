"""Clinical transcript capture using structured LLM output and optional KB labels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from app.models.transcript import TranscriptSymptomAnalysis
from orchestrator.llm.factory import get_chat_model


def _knowledge_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "data"
        / "knowledge"
        / "medical_conditions_simplified.json"
    )


def _load_symptom_catalog_text() -> str:
    path = _knowledge_path()
    if not path.is_file():
        return "(no knowledge file)"
    data = json.loads(path.read_text(encoding="utf-8"))
    lines: list[str] = []
    for cond in data.get("conditions", []):
        cname = cond.get("name", "")
        for sym in cond.get("symptoms", []):
            name = sym.get("name", "")
            descs = sym.get("descriptions") or []
            extra = f"; examples: {', '.join(descs)}" if descs else ""
            lines.append(f"- {name} (condition: {cname}){extra}")
    return "\n".join(lines) if lines else "(empty catalog)"


_SYSTEM_PROMPT = """You extract structured information from clinical transcripts (patient narrative,
nurse intake, vitals, labs/tests, medications, allergies, pregnancy-related statements).

Symptom catalog — use these labels when they fit so names stay consistent with the knowledge base:
{symptom_catalog}

Populate the schema as follows:
- chief_complaint: main reason for contact in one short line.
- patient_stated_concerns: explicit goals, worries, or questions from the patient.
- encounter: type, setting, language, speaker roles only if clear from the text.
- symptoms / negated_symptom_phrases: patient-reported symptoms; mark denials clearly.
- vitals: only values explicitly stated; use string fields to preserve units (e.g. 110/70, 98.4 F).
- test_results: labs, imaging, POC tests as stated (name, value, unit, dates, abnormal wording).
- medications_mentioned / allergies_mentioned: what was said about drugs or reactions.
- pregnancy / intake: fill when pregnancy or nursing/triage content is present.
- unstructured_bullets: important facts that do not fit typed fields (one short bullet each).
- free_text_other: other narrative residue.
- notes: only extraction caveats (ambiguity, missing context, language), not new clinical facts.

Rules:
- Do not invent diagnoses or results; only capture what is stated or clearly implied from the transcript.
- Do not add interpretation beyond summarizing what was said.
- If the transcript language is not English, still prefer catalog English symptom names when they fit.
"""


@tool
def analyze_transcript_symptoms(transcript: str) -> str:
    """Analyze a clinical transcript and return structured JSON (symptoms, vitals, tests, meds, overflow).

    Uses the configured chat model with structured output. Symptom names are aligned to the local
    medical_conditions_simplified catalog when possible. Vitals and test values are captured as stated,
    without adding clinical interpretation. Content that does not fit typed fields goes to
    unstructured_bullets or free_text_other.

    Args:
        transcript: Raw transcript text (patient, nurse, or multi-party).

    Returns:
        JSON string matching TranscriptSymptomAnalysis (nested encounter, vitals, tests, etc.).
    """
    catalog = _load_symptom_catalog_text()
    system = _SYSTEM_PROMPT.format(symptom_catalog=catalog)
    llm = get_chat_model()
    structured = llm.with_structured_output(TranscriptSymptomAnalysis)
    msg = [
        SystemMessage(content=system),
        HumanMessage(
            content=f"Transcript:\n\n{transcript.strip() or '(empty)'}\n\nProduce structured extraction."
        ),
    ]
    try:
        out: Any = structured.invoke(msg)
        if isinstance(out, TranscriptSymptomAnalysis):
            payload = out.model_dump()
        else:
            payload = dict(out) if isinstance(out, dict) else {"raw": str(out)}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


TRANSCRIPT_TOOLS = [analyze_transcript_symptoms]
