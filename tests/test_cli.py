from __future__ import annotations

import errno
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import chdir
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from agent_release_gate.adapters.registry import get_adapter
from agent_release_gate.cli import (
    _prepare_output_target,
    _write_json_atomic,
    run,
)
from agent_release_gate.domain.models import BenchmarkEvidence
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
        self.checkout, self.commit = create_git_repo(self.base)
        self.manifest = write_manifest(self.project_root, self.checkout, self.commit)

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
        self.assertEqual("clawprobench", document["integration"]["adapter"])
        self.assertEqual("SyntheticBench", document["integration"]["name"])
        self.assertNotIn("checkout_path", document["integration"])
        self.assertNotIn(str(self.base), stdout)

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

    def test_adapter_mismatch_returns_two_without_output(self) -> None:
        manifest = write_manifest(
            self.project_root,
            self.checkout,
            self.commit,
            adapter="otherbench",
        )
        output = self.project_root / "decision.json"
        args = self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
        args[args.index("--integration") + 1] = str(manifest)

        code, _, stderr = self.invoke(args)

        self.assertEqual(2, code)
        self.assertIn("does not match integration adapter", stderr)
        self.assertFalse(output.exists())

    def test_output_parent_failure_returns_two(self) -> None:
        output = self.project_root / "missing" / "decision.json"

        code, _, stderr = self.invoke(
            self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
        )

        self.assertEqual(2, code)
        self.assertIn("unable to write decision", stderr)
        self.assertFalse(output.exists())

    def test_output_cannot_overwrite_report(self) -> None:
        report = self.project_root / "report.json"
        original = (FIXTURES / "clawprobench_go.json").read_bytes()
        report.write_bytes(original)

        code, _, stderr = self.invoke(self.evaluate_args(report, report))

        self.assertEqual(2, code)
        self.assertIn("must not overwrite an evaluation input", stderr)
        self.assertEqual(original, report.read_bytes())

    def test_output_cannot_overwrite_policy(self) -> None:
        policy = self.project_root / "policy.toml"
        original = POLICY.read_bytes()
        policy.write_bytes(original)
        args = self.evaluate_args(FIXTURES / "clawprobench_go.json", policy)
        args[args.index("--policy") + 1] = str(policy)

        code, _, stderr = self.invoke(args)

        self.assertEqual(2, code)
        self.assertIn("must not overwrite an evaluation input", stderr)
        self.assertEqual(original, policy.read_bytes())

    def test_output_cannot_overwrite_integration_manifest(self) -> None:
        original = self.manifest.read_bytes()

        code, _, stderr = self.invoke(
            self.evaluate_args(
                FIXTURES / "clawprobench_go.json",
                self.manifest,
            )
        )

        self.assertEqual(2, code)
        self.assertIn("must not overwrite an evaluation input", stderr)
        self.assertEqual(original, self.manifest.read_bytes())

    def test_output_inside_benchmark_checkout_is_rejected_without_write(self) -> None:
        output = self.checkout / "decision.json"

        code, _, stderr = self.invoke(
            self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
        )

        self.assertEqual(2, code)
        self.assertIn("must not be inside the benchmark checkout", stderr)
        self.assertFalse(output.exists())

    def test_output_symlinked_into_benchmark_checkout_is_rejected(self) -> None:
        linked_checkout = self.project_root / "linked-checkout"
        linked_checkout.symlink_to(self.checkout, target_is_directory=True)
        output = linked_checkout / "decision.json"

        code, _, stderr = self.invoke(
            self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
        )

        self.assertEqual(2, code)
        self.assertIn("must not be inside the benchmark checkout", stderr)
        self.assertFalse((self.checkout / "decision.json").exists())

    def test_output_parent_symlink_swap_cannot_redirect_atomic_write(self) -> None:
        safe_directory = self.project_root / "safe"
        safe_directory.mkdir()
        linked_directory = self.project_root / "out"
        linked_directory.symlink_to(safe_directory, target_is_directory=True)
        output = linked_directory / "decision.json"

        with _prepare_output_target(
            output,
            protected_files=(FIXTURES / "clawprobench_go.json", POLICY, self.manifest),
            protected_directory=self.checkout,
        ) as target:
            linked_directory.unlink()
            linked_directory.symlink_to(self.checkout, target_is_directory=True)
            _write_json_atomic(target, {"decision": "go"})

        self.assertEqual(
            {"decision": "go"},
            json.loads((safe_directory / "decision.json").read_text()),
        )
        self.assertFalse((self.checkout / "decision.json").exists())

    def test_input_parent_symlink_swap_cannot_change_or_overwrite_pinned_report(
        self,
    ) -> None:
        reports = self.base / "reports"
        reports.mkdir()
        report = reports / "report.json"
        original_report = (FIXTURES / "clawprobench_go.json").read_bytes()
        report.write_bytes(original_report)
        linked_reports = self.project_root / "linked-reports"
        linked_reports.symlink_to(reports, target_is_directory=True)
        linked_report = linked_reports / "report.json"
        output = self.project_root / "report.json"
        output.write_bytes((FIXTURES / "clawprobench_no_go.json").read_bytes())
        delegate = get_adapter("clawprobench")
        project_root = self.project_root

        class SwappingAdapter:
            def load(
                self,
                report_path: Path,
                *,
                source_version: str,
            ) -> BenchmarkEvidence:
                linked_reports.unlink()
                linked_reports.symlink_to(project_root, target_is_directory=True)
                return delegate.load(report_path, source_version=source_version)

        with patch(
            "agent_release_gate.cli.get_adapter",
            return_value=SwappingAdapter(),
        ):
            code, _, stderr = self.invoke(self.evaluate_args(linked_report, output))

        document = json.loads(output.read_text())
        self.assertEqual(0, code)
        self.assertEqual("", stderr)
        self.assertEqual("go", document["decision"])
        self.assertEqual("agent-go", document["benchmark"]["subject"])
        self.assertEqual(original_report, report.read_bytes())

    def test_input_ancestor_swap_during_pin_is_rejected(self) -> None:
        requested_directory = self.base / "requested"
        requested_inner = requested_directory / "inner"
        requested_inner.mkdir(parents=True)
        report = requested_inner / "report.json"
        report.write_bytes((FIXTURES / "clawprobench_go.json").read_bytes())
        saved_directory = self.base / "saved"
        substitute_directory = self.base / "substitute"
        substitute_inner = substitute_directory / "inner"
        substitute_inner.mkdir(parents=True)
        (substitute_inner / "report.json").write_bytes(
            (FIXTURES / "clawprobench_no_go.json").read_bytes()
        )
        output = self.project_root / "decision.json"
        original_resolve = Path.resolve
        swapped = False

        def resolve_then_swap(path: Path, *args: object, **kwargs: object) -> Path:
            nonlocal swapped
            resolved = original_resolve(path, *args, **kwargs)  # type: ignore[arg-type]
            if path == report and not swapped:
                swapped = True
                requested_directory.rename(saved_directory)
                requested_directory.symlink_to(
                    substitute_directory,
                    target_is_directory=True,
                )
            return resolved

        with patch.object(Path, "resolve", resolve_then_swap):
            code, _, stderr = self.invoke(self.evaluate_args(report, output))

        self.assertEqual(2, code)
        self.assertIn("unable to open evaluation input", stderr)
        self.assertFalse(output.exists())

    def test_validated_checkout_rename_cannot_redirect_output_into_it(self) -> None:
        safe_directory = self.project_root / "safe"
        safe_directory.mkdir()
        output_link = self.project_root / "out"
        output_link.symlink_to(safe_directory, target_is_directory=True)
        output = output_link / "decision.json"
        renamed_checkout = self.base / "RenamedBenchmark"
        original_prepare = _prepare_output_target

        def rename_before_prepare(*args: object, **kwargs: object):
            self.checkout.rename(renamed_checkout)
            self.checkout.mkdir()
            output_link.unlink()
            output_link.symlink_to(renamed_checkout, target_is_directory=True)
            return original_prepare(*args, **kwargs)  # type: ignore[arg-type]

        with patch(
            "agent_release_gate.cli._prepare_output_target",
            side_effect=rename_before_prepare,
        ):
            code, _, stderr = self.invoke(
                self.evaluate_args(FIXTURES / "clawprobench_go.json", output)
            )

        self.assertEqual(2, code)
        self.assertIn("must not be inside the benchmark checkout", stderr)
        self.assertFalse((renamed_checkout / "decision.json").exists())

    def test_output_leaf_symlink_is_replaced_without_overwriting_its_target(self) -> None:
        victim = self.project_root / "victim.txt"
        victim.write_text("keep me\n", encoding="utf-8")
        output = self.project_root / "decision.json"
        output.symlink_to(victim)

        with _prepare_output_target(
            output,
            protected_files=(FIXTURES / "clawprobench_go.json", POLICY, self.manifest),
            protected_directory=self.checkout,
        ) as target:
            _write_json_atomic(target, {"decision": "go"})

        self.assertEqual("keep me\n", victim.read_text())
        self.assertFalse(output.is_symlink())
        self.assertEqual({"decision": "go"}, json.loads(output.read_text()))

    def test_directory_sync_failure_after_replace_does_not_report_failure(self) -> None:
        output = self.project_root / "decision.json"

        with _prepare_output_target(
            output,
            protected_files=(FIXTURES / "clawprobench_go.json", POLICY, self.manifest),
            protected_directory=self.checkout,
        ) as target:
            with patch(
                "agent_release_gate.cli.os.fsync",
                side_effect=(None, OSError(errno.EIO, "simulated directory sync failure")),
            ):
                _write_json_atomic(target, {"decision": "go"})

        self.assertEqual({"decision": "go"}, json.loads(output.read_text()))

    def test_directory_close_failure_after_replace_does_not_report_failure(self) -> None:
        output = self.project_root / "decision.json"
        target = _prepare_output_target(
            output,
            protected_files=(FIXTURES / "clawprobench_go.json", POLICY, self.manifest),
            protected_directory=self.checkout,
        )
        _write_json_atomic(target, {"decision": "go"})

        with patch(
            "agent_release_gate.cli.os.close",
            side_effect=OSError(errno.EIO, "simulated close failure"),
        ):
            target.close()

        self.assertEqual(-1, target.directory_fd)
        self.assertEqual({"decision": "go"}, json.loads(output.read_text()))

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
