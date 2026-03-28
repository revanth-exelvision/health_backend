"""Pydantic models for structured clinical transcript capture (patient + clinician/nurse)."""

from pydantic import BaseModel, Field


class EncounterInfo(BaseModel):
    """High-level context for the encounter if discernible from the transcript."""

    encounter_type: str | None = Field(
        None,
        description="e.g. anc, emergency, phone, follow-up, home visit — as stated or inferred cautiously",
    )
    setting: str | None = Field(None, description="Where the interaction occurred if stated")
    language: str | None = Field(
        None, description="Primary language of the transcript if clear (ISO code or name)"
    )
    speakers_note: str | None = Field(
        None,
        description="Brief note on who said what (patient vs nurse vs doctor) if clear",
    )


class SymptomMention(BaseModel):
    """One symptom or complaint phrase linked to the transcript."""

    name: str = Field(..., description="Canonical or normalized symptom label")
    present: bool = Field(True, description="True if the patient reports it, False if denied")
    negated: bool = Field(False, description="True if explicitly denied in the transcript")
    duration_text: str | None = Field(
        None, description="How long the symptom has lasted, if stated"
    )
    severity_text: str | None = Field(
        None, description="Severity scale or words (e.g. mild, 8/10) if stated"
    )
    onset_text: str | None = Field(None, description="When it started or sudden vs gradual")
    course_text: str | None = Field(
        None, description="Progression: better, worse, unchanged, intermittent, etc."
    )


class VitalSignSet(BaseModel):
    """Vitals or measurements as strings to preserve units and formatting from speech."""

    bp: str | None = Field(None, description="Blood pressure as stated, e.g. 110/70")
    heart_rate: str | None = Field(None, description="Pulse / HR")
    temperature: str | None = Field(None, description="Temperature with unit if stated")
    spo2: str | None = Field(None, description="Oxygen saturation, e.g. 98% on room air")
    respiratory_rate: str | None = Field(None, description="Respiratory rate if stated")
    weight: str | None = Field(None, description="Weight with unit if stated")
    height: str | None = Field(None, description="Height with unit if stated")
    bmi: str | None = Field(None, description="BMI if stated")
    glucose: str | None = Field(None, description="Blood sugar / glucose if stated")


class TestResultMention(BaseModel):
    """Labs, imaging, or point-of-care results as mentioned in the transcript."""

    name: str = Field(..., description="Test or panel name (Hb, USG, urine protein, etc.)")
    value_text: str = Field(
        default="",
        description="Numeric or qualitative result as stated",
    )
    unit: str | None = Field(None, description="Unit if stated")
    reference_or_flag: str | None = Field(
        None, description="Reference range, high/low, or flag as stated in the transcript"
    )
    sample_date_text: str | None = Field(
        None, description="When sample was taken or reported, as stated"
    )
    is_abnormal_mentioned: bool = Field(
        False,
        description="True if the transcript explicitly calls the result abnormal or concerning",
    )
    verbatim_snippet: str | None = Field(
        None, description="Short verbatim quote if useful for audit",
    )


class MedAllergyMention(BaseModel):
    """Medication or allergy line as reported."""

    name: str = Field(..., description="Drug name or allergen")
    dose_or_freq: str | None = Field(None, description="Dose, route, or frequency if stated")
    action: str | None = Field(
        None,
        description="e.g. taking, stopped, PRN, allergic reaction, NKDA — as stated",
    )


class PregnancyContext(BaseModel):
    """Obstetric context when pregnancy is relevant to the transcript."""

    gestational_age_text: str | None = Field(
        None, description="GA or weeks as stated, e.g. 32 weeks"
    )
    gravida_para: str | None = Field(None, description="G/P as stated if any")
    lmp_or_edc_text: str | None = Field(None, description="LMP or EDD if stated")
    fetal_movement_mentioned: bool | None = Field(
        None, description="True/False if fetal movement discussed"
    )
    fetal_movement_detail: str | None = Field(None, description="Details on fetal movement")
    bleeding_mentioned: bool | None = Field(
        None, description="True/False if vaginal bleeding discussed"
    )
    bleeding_detail: str | None = Field(None, description="Details on bleeding if any")


class IntakeCapture(BaseModel):
    """Nurse or intake-style documentation present in the transcript."""

    triage_or_priority_mentioned: str | None = Field(
        None, description="Priority, triage level, or urgency as stated"
    )
    vitals_taken_by_patient_vs_staff: str | None = Field(
        None,
        description="Who measured vitals or if home vs facility — if stated",
    )
    chief_nursing_concern: str | None = Field(
        None, description="Primary nursing concern if clearly stated"
    )


class TranscriptSymptomAnalysis(BaseModel):
    """Structured capture of a clinical transcript: symptoms, vitals, tests, meds, overflow."""

    chief_complaint: str = Field(
        "",
        description="Short summary of the main reason for the encounter",
    )
    patient_stated_concerns: list[str] = Field(
        default_factory=list,
        description="Goals, worries, or questions the patient explicitly raised",
    )
    encounter: EncounterInfo | None = Field(
        default=None,
        description="Encounter context if discernible",
    )
    symptoms: list[SymptomMention] = Field(
        default_factory=list,
        description="Symptoms and relevant patient-reported findings",
    )
    negated_symptom_phrases: list[str] = Field(
        default_factory=list,
        description="Verbatim or near-verbatim phrases where symptoms are denied",
    )
    vitals: VitalSignSet | None = Field(
        default=None,
        description="Vitals only as stated; leave null if none mentioned",
    )
    test_results: list[TestResultMention] = Field(
        default_factory=list,
        description="Labs, imaging, POC tests as stated — not interpreted beyond the transcript",
    )
    medications_mentioned: list[MedAllergyMention] = Field(
        default_factory=list,
        description="Medications discussed (current or historical)",
    )
    allergies_mentioned: list[MedAllergyMention] = Field(
        default_factory=list,
        description="Allergies or adverse reactions discussed",
    )
    pregnancy: PregnancyContext | None = Field(
        default=None,
        description="Pregnancy-related context if applicable",
    )
    intake: IntakeCapture | None = Field(
        default=None,
        description="Nurse intake or triage notes if present in the transcript",
    )
    unstructured_bullets: list[str] = Field(
        default_factory=list,
        description="Important facts that do not fit typed fields (one short bullet per item)",
    )
    free_text_other: str = Field(
        "",
        description="Residual narrative or details that do not fit elsewhere",
    )
    confidence: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="0-1 confidence in this extraction overall",
    )
    notes: str | None = Field(
        None,
        description="Extractor caveats: ambiguity, missing context, language limits — not clinical content",
    )
