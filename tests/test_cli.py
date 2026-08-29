from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import chdir
from datetime import datetime, timezone
from pathlib import Path

from agent_release_gate.cli import run
from tests.support import create_git_repo, write_manifest


FIXTURES = Path(__file__).parent / "fixtures"
POLICY = Path(__file__).parents[1] / "policies" / "default.toml"
NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.project_root = self.base / "agent-release-gate"
        self.project_root.mkdir()
        self.checkout, commit = create_git_repo(self.base)
        self.manifest = write_manifest(self.project_root, self.checkout, commit)

    def invoke(self, args: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with chdir(self.project_root):
            code = run(args, stdout=stdout, stderr=stderr, clock=lambda: NOW)
        return code, stdout.getvalue(), stderr.getvalue()

    def evaluate_args(self, report: Path, output: Path) -> list[str]:
        return [
            "evaluate",
            "--adapter",
            "clawprobench",
            "--report",
            str(report),
            "--policy",
            str(POLICY),
            "--integration",
            str(self.manifest),
            "--output",
            str(output),
        ]

    def test_doctor_emits_json_and_zero_for_valid_integration(self) -> None:
        code, stdout, stderr = self.invoke(
            ["doctor", "--integration", str(self.manifest)]
        )

        document = json.loads(stdout)
        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        self.assertTrue(document["valid"])
        self.assertEqual("SyntheticBench", document["integration"]["name"])

    def test_doctor_reports_invalid_integration_and_returns_two(self) -> None:
        (self.checkout / "dirty.txt").write_text("dirty\n", encoding="utf-8")

        code, stdout, stderr = self.invoke(
            ["doctor", "--integration", str(self.manifest)]
        )

        self.assertEqual(2, code)
        self.assertEqual("", stdout)
        self.assertIn("worktree is not clean", stderr)

    def test_evaluate_go_writes_decision_and_returns_zero(self) -> None:
        output = self.project_root / "decision.json"

        code, stdout, stderr = self.invoke(
            self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
        )

        document = json.loads(output.read_text())
        self.assertEqual(0, code)
        self.assertEqual("", stdout)
        self.assertEqual("", stderr)
        self.assertEqual(1, document["schema_version"])
        self.assertEqual("2026-08-28T12:00:00+00:00", document["evaluated_at"])
        self.assertEqual("go", document["decision"])
        self.assertEqual("clawprobench", document["adapter"])
        self.assertEqual("ClawProBench", document["benchmark"]["name"])
        self.assertEqual("SyntheticBench", document["integration"]["name"])
        self.assertEqual(
            hashlib.sha256(POLICY.read_bytes()).hexdigest(),
            document["policy"]["sha256"],
        )
        self.assertEqual([], document["blockers"])

    def test_evaluate_no_go_writes_all_blockers_and_returns_one(self) -> None:
        report = json.loads((FIXTURES / "clawprobench_no_go.json").read_text())
        report["summary"]["progress"]["requested_scenarios"] = 2
        report_path = self.project_root / "no-go.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")
        output = self.project_root / "decision.json"

        code, _, stderr = self.invoke(self.evaluate_args(report_path, output))

        document = json.loads(output.read_text())
        self.assertEqual(1, code)
        self.assertEqual("", stderr)
        self.assertEqual("no_go", document["decision"])
        self.assertEqual(
            [
                "capability_below_minimum",
                "strict_pass_rate_below_minimum",
                "coverage_below_minimum",
                "safety_gate_failed",
                "execution_failures_exceeded",
            ],
            [blocker["code"] for blocker in document["blockers"]],
        )

    def test_invalid_report_preserves_existing_output_and_returns_two(self) -> None:
        report = self.project_root / "invalid.json"
        report.write_text("{", encoding="utf-8")
        output = self.project_root / "decision.json"
        output.write_text("keep me\n", encoding="utf-8")

        code, _, stderr = self.invoke(self.evaluate_args(report, output))

        self.assertEqual(2, code)
        self.assertIn("invalid JSON", stderr)
        self.assertEqual("keep me\n", output.read_text())

    def test_unknown_adapter_returns_two(self) -> None:
        output = self.project_root / "decision.json"
        args = self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
        args[2] = "unknown"

        code, _, stderr = self.invoke(args)

        self.assertEqual(2, code)
        self.assertIn("unknown adapter", stderr)
        self.assertFalse(output.exists())

    def test_output_parent_failure_returns_two(self) -> None:
        output = self.project_root / "missing" / "decision.json"

        code, _, stderr = self.invoke(
            self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
        )

        self.assertEqual(2, code)
        self.assertIn("unable to write decision", stderr)
        self.assertFalse(output.exists())

    def test_help_is_available_without_loading_inputs(self) -> None:
        code, stdout, stderr = self.invoke(["--help"])

        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        self.assertIn("doctor", stdout)
        self.assertIn("evaluate", stdout)

    def test_invalid_arguments_use_injected_stderr(self) -> None:
        code, stdout, stderr = self.invoke(["evaluate"])

        self.assertEqual(2, code)
        self.assertEqual("", stdout)
        self.assertIn("the following arguments are required", stderr)


if __name__ == "__main__":
    unittest.main()
