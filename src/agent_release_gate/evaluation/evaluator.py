from __future__ import annotations

from agent_release_gate.domain.models import (
    BenchmarkEvidence,
    GateBlocker,
    GateDecision,
    GatePolicy,
)


def evaluate(evidence: BenchmarkEvidence, policy: GatePolicy) -> GateDecision:
    blockers: list[GateBlocker] = []

    if evidence.capability_score < policy.min_capability_score:
        blockers.append(
            GateBlocker(
                code="capability_below_minimum",
                message="Capability score is below the required minimum.",
                expected=policy.min_capability_score,
                observed=evidence.capability_score,
            )
        )
    if evidence.strict_pass_rate < policy.min_strict_pass_rate:
        blockers.append(
            GateBlocker(
                code="strict_pass_rate_below_minimum",
                message="Strict pass rate is below the required minimum.",
                expected=policy.min_strict_pass_rate,
                observed=evidence.strict_pass_rate,
            )
        )
    if evidence.coverage_ratio < policy.min_coverage_ratio:
        blockers.append(
            GateBlocker(
                code="coverage_below_minimum",
                message="Completed scenario coverage is below the required minimum.",
                expected=policy.min_coverage_ratio,
                observed=evidence.coverage_ratio,
            )
        )
    if policy.require_safety_passed and not evidence.safety_passed:
        blockers.append(
            GateBlocker(
                code="safety_gate_failed",
                message="At least one observed trial failed its safety gate.",
                expected=True,
                observed=False,
            )
        )
    if evidence.execution_failures > policy.max_execution_failures:
        blockers.append(
            GateBlocker(
                code="execution_failures_exceeded",
                message="Execution failures exceed the permitted maximum.",
                expected=policy.max_execution_failures,
                observed=evidence.execution_failures,
            )
        )

    return GateDecision(
        decision="go" if not blockers else "no_go",
        evidence=evidence,
        policy=policy,
        blockers=tuple(blockers),
    )
