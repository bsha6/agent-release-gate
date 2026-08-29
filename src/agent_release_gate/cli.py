from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, TextIO

from agent_release_gate.adapters.base import ReportError
from agent_release_gate.adapters.registry import get_adapter
from agent_release_gate.domain.policy import PolicyError, load_policy
from agent_release_gate.evaluation.evaluator import evaluate
from agent_release_gate.integration.validator import (
    IntegrationError,
    load_manifest,
    validate_integration,
)


class DecisionWriteError(ValueError):
    """Raised when a completed decision cannot be written atomically."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-release-gate",
        description="Turn agent benchmark evidence into a release decision.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser(
        "doctor",
        help="Validate a pinned benchmark integration without executing it.",
    )
    doctor.add_argument(
        "--integration",
        type=Path,
        default=Path("integrations/clawprobench.lock.json"),
        help="Integration manifest (default: integrations/clawprobench.lock.json).",
    )

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Evaluate an existing benchmark report against a gate policy.",
    )
    evaluate_parser.add_argument("--adapter", required=True, help="Benchmark adapter name.")
    evaluate_parser.add_argument("--report", required=True, type=Path, help="Benchmark JSON report.")
    evaluate_parser.add_argument(
        "--policy",
        type=Path,
        default=Path("policies/default.toml"),
        help="Gate policy (default: policies/default.toml).",
    )
    evaluate_parser.add_argument(
        "--integration",
        type=Path,
        default=Path("integrations/clawprobench.lock.json"),
        help="Integration manifest (default: integrations/clawprobench.lock.json).",
    )
    evaluate_parser.add_argument("--output", required=True, type=Path, help="Decision JSON path.")
    return parser


def _write_json_atomic(path: Path, document: dict[str, object]) -> None:
    temporary_path: Path | None = None
    try:
        serialized = json.dumps(
            document,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    except (OSError, TypeError, ValueError) as exc:
        raise DecisionWriteError(f"unable to write decision {path}: {exc}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def _validated_integration(path: Path):
    manifest = load_manifest(path, project_root=Path.cwd())
    return validate_integration(manifest)


def _doctor(args: argparse.Namespace, stdout: TextIO) -> int:
    integration = _validated_integration(args.integration)
    document: dict[str, object] = {
        "schema_version": 1,
        "valid": True,
        "integration": integration.to_dict(),
    }
    stdout.write(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return 0


def _evaluate(
    args: argparse.Namespace,
    clock: Callable[[], datetime],
) -> int:
    integration = _validated_integration(args.integration)
    adapter = get_adapter(args.adapter)
    evidence = adapter.load(args.report, source_version=integration.commit)
    policy, policy_sha256 = load_policy(args.policy)
    decision = evaluate(evidence, policy)

    document = decision.to_dict()
    document["schema_version"] = 1
    document["evaluated_at"] = clock().astimezone(timezone.utc).isoformat()
    policy_document = dict(document["policy"])  # type: ignore[arg-type]
    policy_document["sha256"] = policy_sha256
    document["policy"] = policy_document
    document["integration"] = integration.to_dict()
    _write_json_atomic(args.output, document)
    return 0 if decision.decision == "go" else 1


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    clock: Callable[[], datetime] | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    clock = clock or (lambda: datetime.now(timezone.utc))
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    try:
        if args.command == "doctor":
            return _doctor(args, stdout)
        return _evaluate(args, clock)
    except (
        DecisionWriteError,
        IntegrationError,
        PolicyError,
        ReportError,
        OSError,
        ValueError,
    ) as exc:
        stderr.write(f"error: {exc}\n")
        return 2
    except Exception:
        stderr.write("error: unexpected internal failure\n")
        return 2


def main() -> NoReturn:
    raise SystemExit(run())
