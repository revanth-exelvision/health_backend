# Run from repo root: uvicorn app.app:app --host 0.0.0.0 --port 8000
from orchestrator.flow_registry import DEFAULT_FLOWS
from orchestrator.main import create_app
from orchestrator.models import OrchestratorPlan, PlanStep
from orchestrator.tools import DEFAULT_TOOLS

from app.tools import HEALTH_TOOLS


my_flows = {
    "triage_session": (
        "Obstetric triage session",
        "Multi-step triage: merge_symptom_log_for_triage (payload_json with optional rchid, transcript_analysis from analyze_transcript_symptoms, logged_analyses; context may include rchid), rank_conditions_for_symptoms, plan_followups_per_condition, consolidate_triage_output. If the user provides a raw transcript, call analyze_transcript_symptoms first and pass its JSON as transcript_analysis in merge payload. If patient history is missing but is needed for triage: (1) if rchid is unknown but the user gave an exact phone, govrchid, member_id, or name as in registration, call lookup_mother_registration then use the rchid from the row; (2) call fetch_patient_symptom_history with that rchid (or rchid from context) and pass returned analyses as logged_analyses in merge_symptom_log_for_triage (still set rchid and include_csv_log true unless the user opts out).",
        OrchestratorPlan(
            goal_summary="Produce consolidated triage questions, identified/potential conditions, and red flags from the symptom log",
            steps=[
                PlanStep(
                    step_id="1",
                    description="If raw transcript: analyze_transcript_symptoms first. If prior symptom history is not in the chat and triage needs it: resolve rchid via context or lookup_mother_registration (exact filters from user identifiers), then fetch_patient_symptom_history(rchid), then merge_symptom_log_for_triage with logged_analyses from fetch plus any transcript_analysis, rchid, include_csv_log true unless user opts out",
                    tool_name="merge_symptom_log_for_triage",
                    inputs="payload_json string: {rchid?, transcript_analysis?, logged_analyses?, include_csv_log?}; may require prior lookup_mother_registration + fetch_patient_symptom_history",
                    expected_output="TriageSymptomLog JSON",
                ),
                PlanStep(
                    step_id="2",
                    description="Call rank_conditions_for_symptoms with the merge output and top_k 5",
                    tool_name="rank_conditions_for_symptoms",
                    inputs="canonical_symptom_log_json from step 1",
                    expected_output="ranked conditions JSON",
                ),
                PlanStep(
                    step_id="3",
                    description="Call plan_followups_per_condition with log JSON and ranked JSON",
                    tool_name="plan_followups_per_condition",
                    inputs="both JSON strings from prior steps",
                    expected_output="per_condition plans JSON",
                ),
                PlanStep(
                    step_id="4",
                    description="Call consolidate_triage_output with per_condition JSON",
                    tool_name="consolidate_triage_output",
                    inputs="per_condition_plans_json",
                    expected_output="TriageConsolidation JSON",
                ),
            ],
            final_output_description="Summarize questions, identified_conditions, potential_conditions, and red_flags for the user in plain language with decision-support disclaimers",
        ),
    ),
    "analyze_transcript": (
        "Transcript symptom analysis",
        "Extract structured clinical capture from a transcript using analyze_transcript_symptoms; optionally log with append_csv_row to derived/symptom_analysis_log.csv.",
        OrchestratorPlan(
            goal_summary="Analyze the transcript for complaints, vitals, tests, meds, pregnancy/intake cues, and overflow fields",
            steps=[
                PlanStep(
                    step_id="1",
                    description="Call analyze_transcript_symptoms with the transcript text from the user message",
                    tool_name="analyze_transcript_symptoms",
                    inputs="Full transcript text",
                    expected_output="JSON with chief_complaint, symptoms, vitals, test_results, medications/allergies, pregnancy, intake, unstructured_bullets, free_text_other, confidence",
                ),
                PlanStep(
                    step_id="2",
                    description="If the user asked to save or log, call append_csv_row on derived/symptom_analysis_log.csv with analysis_id, created_at, optional rchid, structured_output_json",
                    tool_name="append_csv_row",
                    inputs="Row fields matching the derived CSV header",
                    expected_output="Confirmation JSON from the tool",
                ),
            ],
            final_output_description="A concise natural-language summary of the structured JSON and any logging confirmation",
        ),
    ),
}

app = create_app(
    tools=[*HEALTH_TOOLS],
    flows={**my_flows},
)
