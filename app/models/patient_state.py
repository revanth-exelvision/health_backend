"""PatientState payload for get_patient_state (metadata, history, identified risks)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ActiveConditionItem(BaseModel):
    """Triage KB condition with positive deterministic score from merged patient text."""

    condition: str = Field(..., description="Condition name from medical_conditions_triage.json")
    score: float = Field(
        ...,
        description="Match score from rank_conditions_for_log (not a probability or diagnosis)",
    )


class IdentifiedRisk(BaseModel):
    """Risk signal from patient_risk_signals.json matched to patient text (non-negated lines)."""

    id: str = Field("", description="Stable KB id")
    name: str = Field(..., description="Risk label from KB")
    matched_cues: list[str] = Field(
        default_factory=list,
        description="Risk name and/or history_cues that matched",
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Triage condition names linked to this risk in the KB",
    )


class PatientHistory(BaseModel):
    """Prior structured symptom analyses for the patient."""

    analyses: list[dict[str, Any]] = Field(default_factory=list)
    count: int = Field(0, description="Number of analyses returned")


class PatientMetadata(BaseModel):
    """Registration-backed identity and profile fields."""

    rchid: str = Field(..., description="Mother RCH identifier")
    registration: dict[str, str] = Field(
        default_factory=dict,
        description="Mother registration row (string columns)",
    )


class PatientState(BaseModel):
    """Full patient snapshot for decision-support (not a diagnosis)."""

    metadata: PatientMetadata
    history: PatientHistory
    identified_risks: list[IdentifiedRisk] = Field(default_factory=list)
    active_symptoms: list[str] | None = Field(
        None,
        description="Present, non-negated symptom names from merged history (None if omitted)",
    )
    active_conditions: list[ActiveConditionItem] | None = Field(
        None,
        description="KB conditions with score > 0 from merged history vs medical_conditions_triage.json (None if omitted)",
    )
    search_text_preview: str | None = Field(
        None,
        description="Truncated text used for risk matching (optional, for debugging/agents)",
    )
