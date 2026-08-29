from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, NoReturn

from agent_release_gate.adapters.base import ReportError
from agent_release_gate.domain.models import BenchmarkEvidence, BenchmarkIdentity


def _require_mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReportError(f"{path} must be an object")
    return value


def _require_list(parent: dict[str, Any], key: str, path: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise ReportError(f"{path}.{key} must be an array")
    return value


def _require_string(parent: dict[str, Any], key: str, path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _require_int(parent: dict[str, Any], key: str, path: str) -> int:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportError(f"{path}.{key} must be an integer")
    return value


def _require_ratio(parent: dict[str, Any], key: str, path: str) -> float:
    value = parent.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportError(f"{path}.{key} must be a number")
    ratio = float(value)
    if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
        raise ReportError(f"{path}.{key} must be between 0.0 and 1.0")
    return ratio


def _require_bool(parent: dict[str, Any], key: str, path: str) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        raise ReportError(f"{path}.{key} must be a boolean")
    return value


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"invalid numeric constant {value}")


class ClawProBenchAdapter:
    def load(self, report_path: Path, *, source_version: str) -> BenchmarkEvidence:
        try:
            raw_bytes = report_path.read_bytes()
        except OSError as exc:
            raise ReportError(f"unable to read report {report_path}: {exc}") from exc

        try:
            report = json.loads(
                raw_bytes.decode("utf-8"),
                parse_constant=_reject_json_constant,
            )
        except UnicodeDecodeError as exc:
            raise ReportError(f"report {report_path} is not valid UTF-8: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ReportError(f"report {report_path} contains invalid JSON: {exc}") from exc
        except ValueError as exc:
            raise ReportError(f"report {report_path} contains {exc}") from exc

        root = _require_mapping(report, "report")
        model = _require_string(root, "model", "$")
        timestamp = _require_string(root, "timestamp", "$")
        capability_score = _require_ratio(root, "capability_score", "$")
        strict_pass_rate = _require_ratio(root, "strict_pass_rate", "$")
        total_scenarios = _require_int(root, "total_scenarios", "$")
        scenarios = _require_list(root, "scenarios", "$")

        summary = _require_mapping(root.get("summary"), "$.summary")
        progress = _require_mapping(summary.get("progress"), "$.summary.progress")
        completed_scenarios = _require_int(
            progress,
            "completed_scenarios",
            "$.summary.progress",
        )
        requested_scenarios = _require_int(
            progress,
            "requested_scenarios",
            "$.summary.progress",
        )

        if total_scenarios <= 0 or len(scenarios) != total_scenarios:
            raise ReportError(
                "scenario count mismatch: total_scenarios must be positive and equal len(scenarios)"
            )
        if (
            completed_scenarios <= 0
            or requested_scenarios <= 0
            or completed_scenarios != total_scenarios
            or completed_scenarios > requested_scenarios
        ):
            raise ReportError(
                "progress count mismatch: completed must equal total and not exceed requested"
            )

        safety_passed = True
        execution_failures = 0
        for scenario_index, scenario_value in enumerate(scenarios):
            scenario_path = f"$.scenarios[{scenario_index}]"
            scenario = _require_mapping(scenario_value, scenario_path)
            trials = _require_list(scenario, "trials", scenario_path)
            if not trials:
                raise ReportError(f"{scenario_path}.trials must not be empty")
            for trial_index, trial_value in enumerate(trials):
                trial_path = f"{scenario_path}.trials[{trial_index}]"
                trial = _require_mapping(trial_value, trial_path)
                safety_passed = (
                    _require_bool(trial, "safety_passed", trial_path)
                    and safety_passed
                )
                execution = _require_mapping(
                    trial.get("execution"),
                    f"{trial_path}.execution",
                )
                status = _require_string(execution, "status", f"{trial_path}.execution")
                if status != "success":
                    execution_failures += 1

        if not isinstance(source_version, str) or not source_version.strip():
            raise ReportError("source_version must be a non-empty string")

        identity = BenchmarkIdentity(
            adapter="clawprobench",
            benchmark="ClawProBench",
            subject=model,
            report_timestamp=timestamp,
            report_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            source_version=source_version.strip(),
        )
        return BenchmarkEvidence(
            identity=identity,
            capability_score=capability_score,
            strict_pass_rate=strict_pass_rate,
            completed_scenarios=completed_scenarios,
            requested_scenarios=requested_scenarios,
            safety_passed=safety_passed,
            execution_failures=execution_failures,
        )
