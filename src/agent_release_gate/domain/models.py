from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BenchmarkIdentity:
    adapter: str
    benchmark: str
    subject: str
    report_timestamp: str
    report_sha256: str
    source_version: str


@dataclass(frozen=True, slots=True)
class BenchmarkEvidence:
    identity: BenchmarkIdentity
    capability_score: float
    strict_pass_rate: float
    completed_scenarios: int
    requested_scenarios: int
    safety_passed: bool
    execution_failures: int

    @property
    def coverage_ratio(self) -> float:
        if self.requested_scenarios == 0:
            return 0.0
        return self.completed_scenarios / self.requested_scenarios


@dataclass(frozen=True, slots=True)
class GatePolicy:
    name: str
    min_capability_score: float
    min_strict_pass_rate: float
    min_coverage_ratio: float
    require_safety_passed: bool
    max_execution_failures: int


@dataclass(frozen=True, slots=True)
class GateBlocker:
    code: str
    message: str
    expected: object
    observed: object

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "expected": self.expected,
            "observed": self.observed,
        }


@dataclass(frozen=True, slots=True)
class GateDecision:
    decision: str
    evidence: BenchmarkEvidence
    policy: GatePolicy
    blockers: tuple[GateBlocker, ...]

    def to_dict(self) -> dict[str, object]:
        identity = self.evidence.identity
        return {
            "decision": self.decision,
            "adapter": identity.adapter,
            "benchmark": {
                "name": identity.benchmark,
                "subject": identity.subject,
                "report_timestamp": identity.report_timestamp,
                "report_sha256": identity.report_sha256,
                "source_version": identity.source_version,
            },
            "policy": {
                "name": self.policy.name,
                "min_capability_score": self.policy.min_capability_score,
                "min_strict_pass_rate": self.policy.min_strict_pass_rate,
                "min_coverage_ratio": self.policy.min_coverage_ratio,
                "require_safety_passed": self.policy.require_safety_passed,
                "max_execution_failures": self.policy.max_execution_failures,
            },
            "observed": {
                "capability_score": self.evidence.capability_score,
                "strict_pass_rate": self.evidence.strict_pass_rate,
                "completed_scenarios": self.evidence.completed_scenarios,
                "requested_scenarios": self.evidence.requested_scenarios,
                "coverage_ratio": self.evidence.coverage_ratio,
                "safety_passed": self.evidence.safety_passed,
                "execution_failures": self.evidence.execution_failures,
            },
            "blockers": [blocker.to_dict() for blocker in self.blockers],
        }
