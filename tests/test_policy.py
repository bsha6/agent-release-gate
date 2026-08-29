from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from agent_release_gate.domain.policy import PolicyError, load_policy


VALID_POLICY = """\
[gate]
name = "default"
min_capability_score = 0.70
min_strict_pass_rate = 0.70
min_coverage_ratio = 1.0
require_safety_passed = true
max_execution_failures = 0
"""


class LoadPolicyTests(unittest.TestCase):
    def write_policy(self, contents: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "policy.toml"
        path.write_text(contents, encoding="utf-8")
        return path

    def test_valid_policy_returns_values_and_exact_digest(self) -> None:
        path = self.write_policy(VALID_POLICY)

        policy, digest = load_policy(path)

        self.assertEqual("default", policy.name)
        self.assertEqual(0.70, policy.min_capability_score)
        self.assertEqual(0.70, policy.min_strict_pass_rate)
        self.assertEqual(1.0, policy.min_coverage_ratio)
        self.assertTrue(policy.require_safety_passed)
        self.assertEqual(0, policy.max_execution_failures)
        self.assertEqual(hashlib.sha256(VALID_POLICY.encode()).hexdigest(), digest)

    def test_missing_gate_table_is_rejected(self) -> None:
        path = self.write_policy('[other]\nname = "default"\n')

        with self.assertRaisesRegex(PolicyError, r"exactly the \[gate\] table"):
            load_policy(path)

    def test_unknown_gate_key_is_rejected(self) -> None:
        path = self.write_policy(VALID_POLICY + "unexpected = 1\n")

        with self.assertRaisesRegex(PolicyError, "unknown keys: unexpected"):
            load_policy(path)

    def test_boolean_cannot_be_used_as_numeric_threshold(self) -> None:
        path = self.write_policy(
            VALID_POLICY.replace("min_capability_score = 0.70", "min_capability_score = true")
        )

        with self.assertRaisesRegex(PolicyError, "min_capability_score must be a number"):
            load_policy(path)

    def test_ratio_outside_unit_interval_is_rejected(self) -> None:
        path = self.write_policy(
            VALID_POLICY.replace("min_coverage_ratio = 1.0", "min_coverage_ratio = 1.1")
        )

        with self.assertRaisesRegex(PolicyError, "min_coverage_ratio must be between 0.0 and 1.0"):
            load_policy(path)

    def test_semantic_error_mentions_policy_path(self) -> None:
        path = self.write_policy(
            VALID_POLICY.replace("min_coverage_ratio = 1.0", "min_coverage_ratio = 1.1")
        )

        with self.assertRaises(PolicyError) as caught:
            load_policy(path)

        self.assertIn(str(path), str(caught.exception))

    def test_negative_execution_maximum_is_rejected(self) -> None:
        path = self.write_policy(
            VALID_POLICY.replace("max_execution_failures = 0", "max_execution_failures = -1")
        )

        with self.assertRaisesRegex(PolicyError, "max_execution_failures must be a non-negative integer"):
            load_policy(path)

    def test_blank_name_is_rejected(self) -> None:
        path = self.write_policy(VALID_POLICY.replace('name = "default"', 'name = "  "'))

        with self.assertRaisesRegex(PolicyError, "name must be a non-empty string"):
            load_policy(path)

    def test_malformed_toml_mentions_policy_path(self) -> None:
        path = self.write_policy("[gate\n")

        with self.assertRaisesRegex(PolicyError, str(path)):
            load_policy(path)

    def test_missing_file_mentions_policy_path(self) -> None:
        path = Path("/definitely/missing/release-policy.toml")

        with self.assertRaisesRegex(PolicyError, str(path)):
            load_policy(path)


if __name__ == "__main__":
    unittest.main()
