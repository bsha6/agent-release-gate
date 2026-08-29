from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from collections.abc import Callable, Sequence
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, TextIO

from agent_release_gate.adapters.base import ReportError
from agent_release_gate.adapters.registry import get_adapter
from agent_release_gate.domain.policy import PolicyError, load_policy
from agent_release_gate.evaluation.evaluator import evaluate
from agent_release_gate.integration.validator import (
    IntegrationError,
    IntegrationEvidence,
    load_manifest,
    validate_integration,
)


class DecisionWriteError(ValueError):
    """Raised when a completed decision cannot be written atomically."""


@dataclass(slots=True)
class _OutputTarget:
    directory_fd: int
    name: str
    display_path: Path

    def close(self) -> None:
        directory_fd = self.directory_fd
        self.directory_fd = -1
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                # This read-only guard descriptor cannot affect a committed
                # output, and a close error must not mask the body result.
                pass

    def __enter__(self) -> _OutputTarget:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


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


def _directory_flags() -> int:
    required = ("O_DIRECTORY", "O_NOFOLLOW")
    if any(not hasattr(os, name) for name in required):
        raise DecisionWriteError("secure output writes are not supported on this platform")
    return (
        os.O_RDONLY
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )


def _open_directory(path: Path) -> int:
    return os.open(path, _directory_flags())


def _same_directory(left_fd: int, right_fd: int) -> bool:
    left = os.fstat(left_fd)
    right = os.fstat(right_fd)
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _directory_is_within(directory_fd: int, ancestor: Path) -> bool:
    ancestor_fd = _open_directory(ancestor.resolve(strict=True))
    current_fd = os.dup(directory_fd)
    try:
        while True:
            if _same_directory(current_fd, ancestor_fd):
                return True
            parent_fd = os.open("..", _directory_flags(), dir_fd=current_fd)
            if _same_directory(current_fd, parent_fd):
                os.close(parent_fd)
                return False
            os.close(current_fd)
            current_fd = parent_fd
    finally:
        os.close(current_fd)
        os.close(ancestor_fd)


def _write_json_atomic(
    target: _OutputTarget,
    document: dict[str, object],
) -> None:
    temporary_name: str | None = None
    try:
        serialized = json.dumps(
            document,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
        temporary_name = f".{target.name}.{secrets.token_hex(16)}"
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=target.directory_fd,
        )
        with os.fdopen(
            temporary_fd,
            mode="w",
            encoding="utf-8",
        ) as temporary:
            temporary.write(serialized)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=target.directory_fd,
            dst_dir_fd=target.directory_fd,
        )
        temporary_name = None
        try:
            os.fsync(target.directory_fd)
        except OSError:
            # The rename has already committed the new file. Reporting failure
            # here would falsely promise that an existing output was preserved.
            pass
    except (OSError, TypeError, ValueError) as exc:
        raise DecisionWriteError(
            f"unable to write decision {target.display_path}: {exc}"
        ) from exc
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=target.directory_fd)
            except OSError:
                pass


def _validate_output_path(
    output: Path,
    *,
    protected_files: Sequence[Path],
    protected_directory: Path,
) -> Path:
    resolved_output = output.resolve(strict=False)
    resolved_directory = protected_directory.resolve(strict=False)
    if resolved_output.is_relative_to(resolved_directory):
        raise DecisionWriteError(
            "output path must not be inside the benchmark checkout"
        )
    if any(
        resolved_output == protected.resolve(strict=False)
        for protected in protected_files
    ):
        raise DecisionWriteError(
            "output path must not overwrite an evaluation input"
        )
    return resolved_output


def _prepare_output_target(
    output: Path,
    *,
    protected_files: Sequence[Path],
    protected_directory: Path,
) -> _OutputTarget:
    resolved_output = _validate_output_path(
        output,
        protected_files=protected_files,
        protected_directory=protected_directory,
    )
    output_name = output.name
    if not output_name:
        raise DecisionWriteError("output path must name a file")

    directory_fd: int | None = None
    try:
        directory_fd = _open_directory(output.parent.resolve(strict=False))
        if _directory_is_within(directory_fd, protected_directory):
            raise DecisionWriteError(
                "output path must not be inside the benchmark checkout"
            )

        for protected in protected_files:
            resolved_protected = protected.resolve(strict=False)
            if output_name != resolved_protected.name:
                continue
            protected_parent_fd = _open_directory(resolved_protected.parent)
            try:
                if _same_directory(directory_fd, protected_parent_fd):
                    raise DecisionWriteError(
                        "output path must not overwrite an evaluation input"
                    )
            finally:
                os.close(protected_parent_fd)

        target = _OutputTarget(
            directory_fd=directory_fd,
            name=output_name,
            display_path=output,
        )
        directory_fd = None
        return target
    except DecisionWriteError:
        raise
    except OSError as exc:
        raise DecisionWriteError(f"unable to write decision {output}: {exc}") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _validated_integration(
    path: Path,
    *,
    expected_adapter: str | None = None,
) -> IntegrationEvidence:
    manifest = load_manifest(path, project_root=Path.cwd())
    if expected_adapter is not None and manifest.adapter != expected_adapter:
        raise IntegrationError(
            f"requested adapter {expected_adapter!r} does not match "
            f"integration adapter {manifest.adapter!r}"
        )
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
    adapter = get_adapter(args.adapter)
    integration = _validated_integration(
        args.integration,
        expected_adapter=args.adapter,
    )
    output_target = _prepare_output_target(
        args.output,
        protected_files=(args.report, args.policy, args.integration),
        protected_directory=integration.checkout_path,
    )
    with output_target:
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
        _write_json_atomic(output_target, document)
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
