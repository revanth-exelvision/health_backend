import json
import os
import tempfile
import unittest
from pathlib import Path

from app.services.patient_info import CsvPatientInfoSource
from app.services.risk_signals import (
    build_patient_match_lines,
    match_patient_risk_signals,
)


class TestActiveClinical(unittest.TestCase):
    def test_active_clinical_from_history_analyses(self) -> None:
        from app.services.triage_logic import active_clinical_from_history_analyses

        analyses = [
            {
                "chief_complaint": "bad headache",
                "symptoms": [
                    {"name": "Severe Headache", "present": True, "negated": False},
                ],
                "negated_symptom_phrases": [],
                "unstructured_bullets": [],
                "free_text_other": "",
            }
        ]
        syms, conds = active_clinical_from_history_analyses(
            analyses, rchid="R1", conditions_top_k=8
        )
        self.assertIn("Severe Headache", syms)
        names = [c[0] for c in conds]
        self.assertIn("Preeclampsia", names)


class TestPatientRiskSignals(unittest.TestCase):
    def test_match_finds_non_negated_cue(self) -> None:
        risks = [
            {
                "id": "test_dm",
                "name": "Diabetes risk label",
                "history_cues": ["diabetes"],
                "conditions": ["Gestational Diabetes"],
            }
        ]
        lines = [("history of diabetes in pregnancy", False)]
        out = match_patient_risk_signals(lines, risks=risks)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "test_dm")
        self.assertIn("diabetes", " ".join(out[0].matched_cues).lower())

    def test_match_respects_negated_line(self) -> None:
        risks = [
            {
                "id": "test_lupus",
                "name": "Lupus",
                "history_cues": ["lupus"],
                "conditions": ["Preeclampsia"],
            }
        ]
        lines = [("patient denies systemic lupus", True)]
        out = match_patient_risk_signals(lines, risks=risks)
        self.assertEqual(out, [])

    def test_build_lines_from_registration_and_analysis(self) -> None:
        reg = {"rchid": "R1", "notes": "advanced maternal age"}
        analyses = [
            {
                "chief_complaint": "routine visit",
                "symptoms": [],
                "negated_symptom_phrases": [],
                "unstructured_bullets": [],
                "free_text_other": "",
            }
        ]
        lines = build_patient_match_lines(reg, analyses)
        text = " ".join(t for t, _ in lines).lower()
        self.assertIn("advanced", text)


class TestCsvPatientInfoSource(unittest.TestCase):
    def test_resolve_and_registration_temp_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "mother").mkdir()
            (root / "mother" / "mother registration.csv").write_text(
                "rchid,mobileno\nRCH99,+15550001\n",
                encoding="utf-8",
            )
            old = os.environ.get("MEDICAL_DATA_DIR")
            os.environ["MEDICAL_DATA_DIR"] = str(root)
            try:
                src = CsvPatientInfoSource()
                self.assertEqual(src.resolve_rchid({"mobileno": "+15550001"}), "RCH99")
                reg = src.get_registration("RCH99")
                self.assertIsNotNone(reg)
                assert reg is not None
                self.assertEqual(reg["mobileno"], "+15550001")
            finally:
                if old is None:
                    os.environ.pop("MEDICAL_DATA_DIR", None)
                else:
                    os.environ["MEDICAL_DATA_DIR"] = old


class TestGetPatientStateToolJson(unittest.TestCase):
    def test_tool_returns_error_without_identifier(self) -> None:
        from app.tools.triage_tools import get_patient_state

        raw = get_patient_state.invoke(
            {"rchid": "", "identifiers_json": "", "history_limit": 20}
        )
        data = json.loads(raw)
        self.assertIn("error", data)
