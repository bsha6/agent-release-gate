from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from agent_release_gate.adapters.base import ReportError
from agent_release_gate.adapters.clawprobench import ClawProBenchAdapter
from agent_release_gate.adapters.registry import adapter_names, get_adapter


FIXTURES = Path(__file__).parent / "fixtures"


class ClawProBenchAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = ClawProBenchAdapter()

    def load_fixture(self, name: str = "clawprobench_go.json") -> dict[str, object]:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    def write_report(self, report: object, *, raw: str | None = None) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "report.json"
        path.write_text(raw if raw is not None else json.dumps(report), encoding="utf-8")
        return path

    def test_valid_report_normalizes_metrics_and_identity(self) -> None:
        path = FIXTURES / "clawprobench_go.json"

        evidence = self.adapter.load(path, source_version="abc123")

        self.assertEqual("clawprobench", evidence.identity.adapter)
        self.assertEqual("ClawProBench", evidence.identity.benchmark)
        self.assertEqual("agent-go", evidence.identity.subject)
        self.assertEqual("abc123", evidence.identity.source_version)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), evidence.identity.report_sha256)
        self.assertEqual(0.8, evidence.capability_score)
        self.assertEqual(1.0, evidence.coverage_ratio)
        self.assertTrue(evidence.safety_passed)
        self.assertEqual(0, evidence.execution_failures)

    def test_valid_no_go_report_counts_safety_and_execution_failures(self) -> None:
        evidence = self.adapter.load(
            FIXTURES / "clawprobench_no_go.json",
            source_version="abc123",
        )

        self.assertEqual(0.6, evidence.capability_score)
        self.assertFalse(evidence.safety_passed)
        self.assertEqual(1, evidence.execution_failures)

    def test_registry_exposes_only_clawprobench(self) -> None:
        self.assertEqual(("clawprobench",), adapter_names())
        self.assertIsInstance(get_adapter("clawprobench"), ClawProBenchAdapter)
        with self.assertRaisesRegex(ReportError, "available: clawprobench"):
            get_adapter("unknown")

    def test_unknown_report_fields_are_ignored(self) -> None:
        report = self.load_fixture()
        report["future_field"] = {"safe": True}

        evidence = self.adapter.load(self.write_report(report), source_version="abc123")

        self.assertEqual("agent-go", evidence.identity.subject)

    def test_malformed_or_non_object_json_is_rejected(self) -> None:
        with self.assertRaisesRegex(ReportError, "invalid JSON"):
            self.adapter.load(self.write_report({}, raw="{"), source_version="abc123")
        with self.assertRaisesRegex(ReportError, "report must be an object"):
            self.adapter.load(self.write_report([]), source_version="abc123")

    def test_missing_field_reports_its_path(self) -> None:
        report = self.load_fixture()
        del report["capability_score"]

        with self.assertRaisesRegex(ReportError, r"\$\.capability_score"):
            self.adapter.load(self.write_report(report), source_version="abc123")

    def test_blank_model_is_rejected(self) -> None:
        report = self.load_fixture()
        report["model"] = "  "

        with self.assertRaisesRegex(ReportError, r"\$\.model must be a non-empty string"):
            self.adapter.load(self.write_report(report), source_version="abc123")

    def test_boolean_and_non_finite_scores_are_rejected(self) -> None:
        report = self.load_fixture()
        report["capability_score"] = True
        with self.assertRaisesRegex(ReportError, r"\$\.capability_score must be a number"):
            self.adapter.load(self.write_report(report), source_version="abc123")

        raw = (FIXTURES / "clawprobench_go.json").read_text().replace("0.8", "NaN", 1)
        with self.assertRaisesRegex(ReportError, "invalid numeric constant"):
            self.adapter.load(self.write_report({}, raw=raw), source_version="abc123")

    def test_score_outside_unit_interval_is_rejected(self) -> None:
        report = self.load_fixture()
        report["strict_pass_rate"] = 1.1

        with self.assertRaisesRegex(ReportError, r"\$\.strict_pass_rate must be between 0.0 and 1.0"):
            self.adapter.load(self.write_report(report), source_version="abc123")

    def test_scenario_and_progress_count_mismatches_are_rejected(self) -> None:
        report = self.load_fixture()
        report["total_scenarios"] = 2
        with self.assertRaisesRegex(ReportError, "scenario count mismatch"):
            self.adapter.load(self.write_report(report), source_version="abc123")

        report = self.load_fixture()
        report["summary"]["progress"]["completed_scenarios"] = 0
        with self.assertRaisesRegex(ReportError, "progress count mismatch"):
            self.adapter.load(self.write_report(report), source_version="abc123")

    def test_empty_trials_are_rejected(self) -> None:
        report = self.load_fixture()
        report["scenarios"][0]["trials"] = []

        with self.assertRaisesRegex(ReportError, r"\$\.scenarios\[0\]\.trials must not be empty"):
            self.adapter.load(self.write_report(report), source_version="abc123")

    def test_trial_safety_and_execution_status_are_required(self) -> None:
        report = self.load_fixture()
        del report["scenarios"][0]["trials"][0]["safety_passed"]
        with self.assertRaisesRegex(ReportError, "safety_passed must be a boolean"):
            self.adapter.load(self.write_report(report), source_version="abc123")

        report = self.load_fixture()
        del report["scenarios"][0]["trials"][0]["execution"]["status"]
        with self.assertRaisesRegex(ReportError, "status must be a non-empty string"):
            self.adapter.load(self.write_report(report), source_version="abc123")


if __name__ == "__main__":
    unittest.main()
