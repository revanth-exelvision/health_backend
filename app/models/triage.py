"""Pydantic models for obstetric triage (symptom log, ranking, follow-up plans, consolidation)."""

from pydantic import BaseModel, Field


class MergedSymptomLine(BaseModel):
    """Single merged symptom entry from one or more transcript analyses."""

    name: str = Field(..., description="Symptom label")
    present: bool = Field(True, description="Patient affirms the symptom")
    negated: bool = Field(False, description="Patient denies this symptom")


class TriageSymptomLog(BaseModel):
    """Canonical symptom + context blob for ranking and LLM triage steps."""

    rchid: str | None = Field(None, description="Mother RCH ID if known")
    symptoms: list[MergedSymptomLine] = Field(default_factory=list)
    chief_complaint: str = ""
    negated_symptom_phrases: list[str] = Field(default_factory=list)
    vitals_summary: str = Field(
        "",
        description="Plain-text summary of vitals for matching (not diagnosis)",
    )
    tests_summary: str = Field("", description="Plain-text summary of tests mentioned")
    unstructured_bullets: list[str] = Field(default_factory=list)
    free_text_other: str = ""
    source_notes: list[str] = Field(
        default_factory=list,
        description="How this log was built (e.g. merged from N analyses)",
    )


class RankedCondition(BaseModel):
    """One condition with deterministic match score from the KB."""

    condition: str
    score: float
    matched_symptoms: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)


class ConditionRankingResult(BaseModel):
    ranked: list[RankedCondition] = Field(default_factory=list)


class PerConditionTriagePlan(BaseModel):
    """Follow-up plan for one condition after individual evaluation."""

    condition_name: str
    questions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(
        default_factory=list,
        description="KB-grounded symptoms that strongly support this condition if reported",
    )
    red_flags_present_in_log: list[str] = Field(default_factory=list)
    red_flags_still_to_verify: list[str] = Field(default_factory=list)
    already_addressed: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class PerConditionPlansBundle(BaseModel):
    """Wrapper for tool output between plan_followups and consolidate."""

    per_condition: list[PerConditionTriagePlan] = Field(default_factory=list)


class TriageConsolidation(BaseModel):
    """Final merged triage output for the client."""

    questions: list[str] = Field(
        default_factory=list,
        description="Single flat list of next questions; do not group or prefix by condition name",
    )
    identified_conditions: list[str] = Field(
        default_factory=list,
        description="Conditions strongly supported by red flags already in the log",
    )
    potential_conditions: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(
        default_factory=list,
        description="Single flat list of condition-confirming findings; do not group or prefix by condition",
    )
    rationale_brief: str | None = Field(
        None,
        description="Short decision-support summary; not a diagnosis",
    )
