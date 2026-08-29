from __future__ import annotations

import unittest

from agent_release_gate.domain.models import (
    BenchmarkEvidence,
    BenchmarkIdentity,
    GatePolicy,
)
from agent_release_gate.evaluation.evaluator import evaluate


class EvaluateTests(unittest.TestCase):
    def identity(self) -> BenchmarkIdentity:
        return BenchmarkIdentity(
            adapter="example",
            benchmark="ExampleBench",
            subject="agent-v1",
            report_timestamp="2026-08-27T12:00:00+00:00",
            report_sha256="a" * 64,
            source_version="benchmark-v1",
        )

    def evidence(self, **overrides: object) -> BenchmarkEvidence:
        values: dict[str, object] = {
            "identity": self.identity(),
            "capability_score": 0.80,
            "strict_pass_rate": 0.80,
            "completed_scenarios": 10,
            "requested_scenarios": 10,
            "safety_passed": True,
            "execution_failures": 0,
        }
        values.update(overrides)
        return BenchmarkEvidence(**values)  # type: ignore[arg-type]

    def policy(self, **overrides: object) -> GatePolicy:
        values: dict[str, object] = {
            "name": "default",
            "min_capability_score": 0.70,
            "min_strict_pass_rate": 0.70,
            "min_coverage_ratio": 1.0,
            "require_safety_passed": True,
            "max_execution_failures": 0,
        }
        values.update(overrides)
        return GatePolicy(**values)  # type: ignore[arg-type]

    def test_all_thresholds_met_returns_go(self) -> None:
        decision = evaluate(self.evidence(), self.policy())

        self.assertEqual("go", decision.decision)
        self.assertEqual((), decision.blockers)

    def test_threshold_equality_returns_go(self) -> None:
        evidence = self.evidence(capability_score=0.70, strict_pass_rate=0.70)

        decision = evaluate(evidence, self.policy())

        self.assertEqual("go", decision.decision)

    def test_all_failed_rules_are_returned_in_policy_order(self) -> None:
        evidence = self.evidence(
            capability_score=0.69,
            strict_pass_rate=0.68,
            completed_scenarios=9,
            safety_passed=False,
            execution_failures=2,
        )

        decision = evaluate(evidence, self.policy())

        self.assertEqual("no_go", decision.decision)
        self.assertEqual(
            [
                "capability_below_minimum",
                "strict_pass_rate_below_minimum",
                "coverage_below_minimum",
                "safety_gate_failed",
                "execution_failures_exceeded",
            ],
            [blocker.code for blocker in decision.blockers],
        )

    def test_safety_rule_can_be_disabled(self) -> None:
        decision = evaluate(
            self.evidence(safety_passed=False),
            self.policy(require_safety_passed=False),
        )

        self.assertEqual("go", decision.decision)

    def test_decision_dict_contains_identity_metrics_and_blockers(self) -> None:
        result = evaluate(
            self.evidence(capability_score=0.50),
            self.policy(),
        ).to_dict()

        self.assertEqual("no_go", result["decision"])
        self.assertEqual("ExampleBench", result["benchmark"]["name"])
        self.assertEqual(0.50, result["observed"]["capability_score"])
        self.assertEqual("default", result["policy"]["name"])
        self.assertEqual(
            "capability_below_minimum",
            result["blockers"][0]["code"],
        )


if __name__ == "__main__":
    unittest.main()
