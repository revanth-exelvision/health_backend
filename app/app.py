# Run from repo root: uvicorn app.app:app --host 0.0.0.0 --port 8000
from orchestrator.flow_registry import DEFAULT_FLOWS
from orchestrator.main import create_app
from orchestrator.models import OrchestratorPlan, PlanStep
from orchestrator.logging_setup import configure_logging, get_logger
from orchestrator.tools import DEFAULT_TOOLS

from app.tools import HEALTH_TOOLS

configure_logging()
logger = get_logger(__name__)


my_flows = {
    "triage_session": (
        "Obstetric triage session",
        "Patient-aware triage: request context may include ``patient_state`` (full PatientState JSON from a gateway) and/or ``rchid`` / registration identifiers. If ``patient_state`` is absent but ``rchid`` or identifiers are available, call ``get_patient_state`` first. Use that snapshot (metadata, history, identified_risks, active_symptoms, active_conditions) to inform the session. Then merge_symptom_log_for_triage, rank, plan follow-ups, consolidate. If the user provides a raw transcript, call analyze_transcript_symptoms and pass its JSON as transcript_analysis in the merge payload. For logged analyses prefer history.analyses from patient state when present; otherwise fetch_patient_symptom_history or lookup_mother_registration as before.",
        OrchestratorPlan(
            goal_summary="Produce consolidated triage output using patient state (when provided or loaded) plus the current symptom log",
            steps=[
                PlanStep(
                    step_id="1",
                    description="Establish patient state: if context already contains patient_state, use it; else if rchid or identifiers_json can be taken from context or the user message, call get_patient_state (optional include_active_clinical). Skip only if no identifier is available.",
                    tool_name="get_patient_state",
                    inputs="rchid and/or identifiers_json from context or user; align with context.patient_state when preloaded",
                    expected_output="PatientState JSON or skipped when impossible",
                ),
                PlanStep(
                    step_id="2",
                    description="If raw transcript in the user message: analyze_transcript_symptoms first. Build merge_symptom_log_for_triage payload with rchid, optional transcript_analysis, logged_analyses from patient_state.history.analyses and/or fetch_patient_symptom_history / lookup as needed, include_csv_log true unless user opts out",
                    tool_name="merge_symptom_log_for_triage",
                    inputs="payload_json: {rchid?, transcript_analysis?, logged_analyses?, include_csv_log?}; may use analyses from step 1 patient state",
                    expected_output="TriageSymptomLog JSON",
                ),
                PlanStep(
                    step_id="3",
                    description="Call rank_conditions_for_symptoms with the merge output and top_k 5",
                    tool_name="rank_conditions_for_symptoms",
                    inputs="canonical_symptom_log_json from step 2",
                    expected_output="ranked conditions JSON",
                ),
                PlanStep(
                    step_id="4",
                    description="Call plan_followups_per_condition with log JSON and ranked JSON",
                    tool_name="plan_followups_per_condition",
                    inputs="both JSON strings from prior steps",
                    expected_output="per_condition plans JSON",
                ),
                PlanStep(
                    step_id="5",
                    description="Call consolidate_triage_output with per_condition JSON; you may reference patient state from step 1 when summarizing risks/context",
                    tool_name="consolidate_triage_output",
                    inputs="per_condition_plans_json",
                    expected_output="TriageConsolidation JSON",
                ),
            ],
            final_output_description="Summarize questions, identified_conditions, potential_conditions, red_flags, and how they relate to known patient state (metadata/history/risks) when available; decision-support disclaimers",
        ),
    ),
    "analyze_transcript": (
        "Transcript symptom analysis",
        "Request context may include ``patient_state`` (full PatientState JSON) and/or ``rchid``. If ``patient_state`` is absent but ``rchid`` or registration identifiers are in context or the message, call ``get_patient_state`` first so analysis can be interpreted alongside metadata, history, identified_risks, and active_symptoms/active_conditions. Then extract structured capture with analyze_transcript_symptoms; optionally log with append_csv_row.",
        OrchestratorPlan(
            goal_summary="Analyze the transcript in the context of patient state when available",
            steps=[
                PlanStep(
                    step_id="1",
                    description="Establish patient state: use context.patient_state if present; else if rchid or identifiers_json is available from context or user message, call get_patient_state. If no identifier, skip.",
                    tool_name="get_patient_state",
                    inputs="rchid / identifiers_json / preloaded patient_state in context",
                    expected_output="PatientState JSON or skip",
                ),
                PlanStep(
                    step_id="2",
                    description="Call analyze_transcript_symptoms with the transcript text; relate findings to patient state from step 1 when available",
                    tool_name="analyze_transcript_symptoms",
                    inputs="Full transcript text from the user message",
                    expected_output="JSON with chief_complaint, symptoms, vitals, test_results, medications/allergies, pregnancy, intake, unstructured_bullets, free_text_other, confidence",
                ),
                PlanStep(
                    step_id="3",
                    description="If the user asked to save or log, call append_csv_row on derived/symptom_analysis_log.csv with analysis_id, created_at, optional rchid from context/patient state, structured_output_json",
                    tool_name="append_csv_row",
                    inputs="Row fields matching the derived CSV header",
                    expected_output="Confirmation JSON from the tool",
                ),
            ],
            final_output_description="Concise summary of structured extraction and how it compares or adds to patient state (history/risks/active clinical) when step 1 ran; include logging confirmation if applicable",
        ),
    ),
    "patient_info_risk": (
        "Patient state: metadata, history, identified risks",
        "Load patient metadata and symptom history, then match patient_risk_signals KB. Call get_patient_state with rchid from context or identifiers_json (exact mother registration filters). Return the PatientState JSON: metadata, history, identified_risks, and optionally active_symptoms and active_conditions (from merged history vs medical_conditions_triage.json). This is decision-support only, not a diagnosis.",
        OrchestratorPlan(
            goal_summary="Return PatientState with metadata, history, and KB-identified risk signals",
            steps=[
                PlanStep(
                    step_id="1",
                    description="Call get_patient_state: pass rchid from context if present, else identifiers_json from the user message (non-empty JSON object with exact column filters)",
                    tool_name="get_patient_state",
                    inputs="rchid and/or identifiers_json; optional history_limit, include_active_clinical, conditions_top_k",
                    expected_output="PatientState JSON (metadata, history, identified_risks; optional active_symptoms, active_conditions, search_text_preview)",
                ),
            ],
            final_output_description="Summarize metadata, history count, and identified_risks in plain language with decision-support disclaimers; do not diagnose",
        ),
    ),
}

logger.info(
    "health_backend: registering named flows %s",
    ", ".join(sorted(my_flows.keys())),
)

app = create_app(
    tools=[*HEALTH_TOOLS],
    flows={**my_flows},
)
