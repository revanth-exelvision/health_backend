import json
import unittest

from app.models.triage import MergedSymptomLine, TriageSymptomLog
from app.services.triage_logic import merge_symptom_log_payload, rank_conditions_for_log


class TestTriageRanking(unittest.TestCase):
    def test_preeclampsia_signals_rank_high(self) -> None:
        log = TriageSymptomLog(
            symptoms=[
                MergedSymptomLine(name="Severe Headache", present=True, negated=False),
                MergedSymptomLine(name="Visual Disturbance", present=True, negated=False),
            ],
            chief_complaint="headache and blurry vision",
        )
        result = rank_conditions_for_log(log, top_k=8)
        self.assertTrue(result.ranked)
        top_names = [r.condition for r in result.ranked[:3]]
        self.assertIn(
            "Preeclampsia",
            top_names,
            msg=f"Expected Preeclampsia in top conditions, got {top_names}",
        )
        pree = next(r for r in result.ranked if r.condition == "Preeclampsia")
        self.assertGreater(pree.score, 0)
        self.assertTrue(pree.matched_symptoms)

    def test_negated_symptom_reduces_score(self) -> None:
        log = TriageSymptomLog(
            symptoms=[
                MergedSymptomLine(name="Severe Headache", present=False, negated=True),
            ],
            chief_complaint="routine visit",
        )
        result = rank_conditions_for_log(log, top_k=100)
        pree = next((r for r in result.ranked if r.condition == "Preeclampsia"), None)
        self.assertIsNotNone(pree)
        self.assertLessEqual(pree.score, 0.0)

    def test_merge_payload_transcript_only(self) -> None:
        payload = {
            "transcript_analysis": {
                "chief_complaint": "burning when peeing",
                "symptoms": [
                    {"name": "Dysuria", "present": True, "negated": False},
                ],
                "negated_symptom_phrases": [],
            },
            "include_csv_log": False,
        }
        log = merge_symptom_log_payload(payload)
        self.assertEqual(len(log.symptoms), 1)
        self.assertIn("Dysuria", log.symptoms[0].name)
        result = rank_conditions_for_log(log, top_k=5)
        names = [r.condition for r in result.ranked[:3]]
        self.assertIn("Infections", names)


class TestTriageToolsSmoke(unittest.TestCase):
    def test_rank_tool_returns_valid_json(self) -> None:
        from app.tools.triage_tools import rank_conditions_for_symptoms

        log = TriageSymptomLog(
            symptoms=[MergedSymptomLine(name="Hypertension", present=True, negated=False)]
        )
        raw = rank_conditions_for_symptoms.invoke(
            {"canonical_symptom_log_json": log.model_dump_json(), "top_k": 3}
        )
        data = json.loads(raw)
        self.assertIn("ranked", data)
        self.assertEqual(len(data["ranked"]), 3)


if __name__ == "__main__":
    unittest.main()
