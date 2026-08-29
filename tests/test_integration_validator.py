from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_release_gate.integration.validator import (
    IntegrationError,
    IntegrationManifest,
    load_manifest,
    validate_integration,
)
from tests.support import TEST_ORIGIN, create_git_repo, run_git, write_manifest


class IntegrationValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.project_root = self.base / "agent-release-gate"
        self.project_root.mkdir()
        self.checkout, self.commit = create_git_repo(self.base)

    def manifest(self, **kwargs: object) -> IntegrationManifest:
        checkout = kwargs.pop("checkout", self.checkout)
        commit = kwargs.pop("commit", self.commit)
        path = write_manifest(
            self.project_root,
            checkout,  # type: ignore[arg-type]
            commit,  # type: ignore[arg-type]
            **kwargs,  # type: ignore[arg-type]
        )
        return load_manifest(path, project_root=self.project_root)

    def test_valid_checkout_returns_provenance(self) -> None:
        evidence = validate_integration(self.manifest())

        self.assertEqual("clawprobench", evidence.adapter)
        self.assertEqual("SyntheticBench", evidence.name)
        self.assertEqual(self.checkout.resolve(), evidence.checkout_path)
        self.assertEqual(TEST_ORIGIN, evidence.repository_url)
        self.assertEqual(self.commit, evidence.commit)
        self.assertEqual(self.commit, evidence.to_dict()["commit"])

    def test_missing_or_non_git_checkout_is_rejected(self) -> None:
        missing = self.base / "Missing"
        with self.assertRaisesRegex(IntegrationError, "checkout does not exist"):
            validate_integration(self.manifest(checkout=missing))

        nongit = self.base / "NotGit"
        nongit.mkdir()
        with self.assertRaisesRegex(IntegrationError, "not a Git worktree"):
            validate_integration(self.manifest(checkout=nongit))

    def test_wrong_commit_and_origin_are_rejected(self) -> None:
        wrong_commit = "0" * 40
        with self.assertRaisesRegex(IntegrationError, f"expected commit {wrong_commit}"):
            validate_integration(self.manifest(commit=wrong_commit))

        with self.assertRaisesRegex(IntegrationError, "unexpected origin URL"):
            validate_integration(self.manifest(repository_url="https://example.com/other.git"))

    def test_dirty_worktree_is_rejected(self) -> None:
        (self.checkout / "untracked.txt").write_text("dirty\n", encoding="utf-8")

        with self.assertRaisesRegex(IntegrationError, "worktree is not clean"):
            validate_integration(self.manifest())

    def test_validation_does_not_refresh_or_rewrite_git_index(self) -> None:
        index_path = self.checkout / ".git" / "index"
        before = index_path.read_bytes()
        os.utime(self.checkout / "README.md", (1_577_836_800, 1_577_836_800))

        validate_integration(self.manifest())

        self.assertEqual(before, index_path.read_bytes())

    def test_inherited_git_repository_context_cannot_override_checkout(self) -> None:
        alternate_parent = self.base / "alternate"
        alternate_parent.mkdir()
        alternate_checkout, _ = create_git_repo(alternate_parent)
        (alternate_checkout / "alternate.txt").write_text("distinct repository\n", encoding="utf-8")
        run_git(alternate_checkout, "add", "alternate.txt")
        run_git(alternate_checkout, "commit", "-m", "test: distinguish alternate repository")

        with patch.dict(
            "os.environ",
            {
                "GIT_DIR": str(alternate_checkout / ".git"),
                "GIT_WORK_TREE": str(alternate_checkout),
                "GIT_INDEX_FILE": str(alternate_checkout / ".git" / "index"),
            },
        ):
            evidence = validate_integration(self.manifest())

        self.assertEqual(self.checkout.resolve(), evidence.checkout_path)
        self.assertEqual(self.commit, evidence.commit)

    def test_prohibited_directory_is_rejected(self) -> None:
        (self.checkout / "vendor").mkdir()

        with self.assertRaisesRegex(IntegrationError, "prohibited path is present: vendor"):
            validate_integration(self.manifest())

    def test_validation_aggregates_independent_mismatches(self) -> None:
        (self.checkout / "vendor").mkdir()
        (self.checkout / "dirty.txt").write_text("dirty\n", encoding="utf-8")
        run_git(self.checkout, "remote", "set-url", "origin", "https://example.com/wrong.git")

        with self.assertRaises(IntegrationError) as caught:
            validate_integration(self.manifest())

        message = str(caught.exception)
        self.assertIn("unexpected origin URL", message)
        self.assertIn("worktree is not clean", message)
        self.assertIn("prohibited path is present: vendor", message)

    def test_manifest_rejects_unknown_or_missing_keys(self) -> None:
        path = write_manifest(
            self.project_root,
            self.checkout,
            self.commit,
            updates={"unknown": True},
        )
        with self.assertRaisesRegex(IntegrationError, "unknown keys: unknown"):
            load_manifest(path, project_root=self.project_root)

        data = json.loads(path.read_text())
        del data["name"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(IntegrationError, "missing keys: name"):
            load_manifest(path, project_root=self.project_root)

        path = write_manifest(self.project_root, self.checkout, self.commit)
        data = json.loads(path.read_text())
        del data["adapter"]
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(IntegrationError, "missing keys: adapter"):
            load_manifest(path, project_root=self.project_root)

    def test_manifest_rejects_unsafe_paths_and_commit(self) -> None:
        with self.assertRaisesRegex(IntegrationError, "schema_version must be integer 1"):
            self.manifest(updates={"schema_version": 1.0})
        with self.assertRaisesRegex(IntegrationError, "checkout_path must be relative"):
            self.manifest(updates={"checkout_path": str(self.checkout.resolve())})
        with self.assertRaisesRegex(IntegrationError, "checkout_path must resolve to a direct sibling"):
            self.manifest(updates={"checkout_path": "../../escape"})
        with self.assertRaisesRegex(IntegrationError, "commit must be 40 lowercase hexadecimal"):
            self.manifest(updates={"commit": "ABC"})
        with self.assertRaisesRegex(IntegrationError, "prohibited_paths entries must be safe relative paths"):
            self.manifest(prohibited_paths=["../escape"])

    def test_manifest_rejects_unsafe_adapter_names(self) -> None:
        for adapter in ("ClawProBench", "claw pro bench", "-clawprobench"):
            with self.subTest(adapter=adapter):
                with self.assertRaisesRegex(
                    IntegrationError,
                    "adapter must be a lowercase identifier",
                ):
                    self.manifest(updates={"adapter": adapter})


if __name__ == "__main__":
    unittest.main()
