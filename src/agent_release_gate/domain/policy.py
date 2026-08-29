from __future__ import annotations

import hashlib
import math
import tomllib
from pathlib import Path
from typing import Any

from agent_release_gate.domain.models import GatePolicy


class PolicyError(ValueError):
    """Raised when a release-gate policy cannot be loaded safely."""


_GATE_KEYS = {
    "name",
    "min_capability_score",
    "min_strict_pass_rate",
    "min_coverage_ratio",
    "require_safety_passed",
    "max_execution_failures",
}


def _require_ratio(gate: dict[str, Any], key: str) -> float:
    value = gate.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyError(f"{key} must be a number")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise PolicyError(f"{key} must be between 0.0 and 1.0")
    return value


def load_policy(path: Path) -> tuple[GatePolicy, str]:
    try:
        raw_bytes = path.read_bytes()
        raw = tomllib.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise PolicyError(f"unable to load policy {path}: {exc}") from exc

    try:
        if set(raw) != {"gate"} or not isinstance(raw.get("gate"), dict):
            raise PolicyError("policy must contain exactly the [gate] table")

        gate = raw["gate"]
        missing = sorted(_GATE_KEYS - set(gate))
        unknown = sorted(set(gate) - _GATE_KEYS)
        if missing:
            raise PolicyError(f"policy gate is missing keys: {', '.join(missing)}")
        if unknown:
            raise PolicyError(f"policy gate has unknown keys: {', '.join(unknown)}")

        name = gate["name"]
        if not isinstance(name, str) or not name.strip():
            raise PolicyError("name must be a non-empty string")

        require_safety_passed = gate["require_safety_passed"]
        if not isinstance(require_safety_passed, bool):
            raise PolicyError("require_safety_passed must be a boolean")

        max_execution_failures = gate["max_execution_failures"]
        if (
            isinstance(max_execution_failures, bool)
            or not isinstance(max_execution_failures, int)
            or max_execution_failures < 0
        ):
            raise PolicyError("max_execution_failures must be a non-negative integer")

        policy = GatePolicy(
            name=name.strip(),
            min_capability_score=_require_ratio(gate, "min_capability_score"),
            min_strict_pass_rate=_require_ratio(gate, "min_strict_pass_rate"),
            min_coverage_ratio=_require_ratio(gate, "min_coverage_ratio"),
            require_safety_passed=require_safety_passed,
            max_execution_failures=max_execution_failures,
        )
    except PolicyError as exc:
        raise PolicyError(f"invalid policy {path}: {exc}") from exc
    return policy, hashlib.sha256(raw_bytes).hexdigest()
