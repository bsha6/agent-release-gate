from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class IntegrationError(ValueError):
    """Raised when benchmark provenance cannot be established."""


@dataclass(frozen=True, slots=True)
class IntegrationManifest:
    adapter: str
    name: str
    repository_url: str
    checkout_path: Path
    commit: str
    prohibited_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntegrationEvidence:
    adapter: str
    name: str
    checkout_path: Path
    repository_url: str
    commit: str

    def to_dict(self) -> dict[str, object]:
        return {
            "adapter": self.adapter,
            "name": self.name,
            "repository_url": self.repository_url,
            "commit": self.commit,
        }


_MANIFEST_KEYS = {
    "schema_version",
    "adapter",
    "name",
    "repository_url",
    "checkout_path",
    "commit",
    "prohibited_paths",
}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_ADAPTER_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def _nonempty_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IntegrationError(f"{key} must be a non-empty string")
    return value.strip()


def load_manifest(path: Path, *, project_root: Path) -> IntegrationManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrationError(f"unable to load integration manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise IntegrationError("integration manifest must be an object")

    missing = sorted(_MANIFEST_KEYS - set(raw))
    unknown = sorted(set(raw) - _MANIFEST_KEYS)
    if missing:
        raise IntegrationError(f"integration manifest has missing keys: {', '.join(missing)}")
    if unknown:
        raise IntegrationError(f"integration manifest has unknown keys: {', '.join(unknown)}")

    schema_version = raw["schema_version"]
    if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version != 1:
        raise IntegrationError("schema_version must be integer 1")

    adapter = _nonempty_string(raw, "adapter")
    if not _ADAPTER_RE.fullmatch(adapter):
        raise IntegrationError("adapter must be a lowercase identifier")

    name = _nonempty_string(raw, "name")
    repository_url = _nonempty_string(raw, "repository_url")
    checkout_raw = _nonempty_string(raw, "checkout_path")
    checkout_relative = Path(checkout_raw)
    if checkout_relative.is_absolute():
        raise IntegrationError("checkout_path must be relative")

    resolved_project_root = project_root.resolve()
    checkout_path = (resolved_project_root / checkout_relative).resolve()
    if checkout_path.parent != resolved_project_root.parent:
        raise IntegrationError("checkout_path must resolve to a direct sibling of the project")

    commit = _nonempty_string(raw, "commit")
    if not _COMMIT_RE.fullmatch(commit):
        raise IntegrationError("commit must be 40 lowercase hexadecimal characters")

    prohibited_raw = raw["prohibited_paths"]
    if not isinstance(prohibited_raw, list):
        raise IntegrationError("prohibited_paths must be an array")
    prohibited_paths: list[str] = []
    for value in prohibited_raw:
        if not isinstance(value, str) or not value.strip():
            raise IntegrationError("prohibited_paths entries must be safe relative paths")
        normalized = PurePosixPath(value.strip())
        if normalized.is_absolute() or ".." in normalized.parts or "." in normalized.parts:
            raise IntegrationError("prohibited_paths entries must be safe relative paths")
        prohibited_paths.append(normalized.as_posix())

    return IntegrationManifest(
        adapter=adapter,
        name=name,
        repository_url=repository_url,
        checkout_path=checkout_path,
        commit=commit,
        prohibited_paths=tuple(prohibited_paths),
    )


def _git(checkout: Path, *args: str) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-C",
            str(checkout),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def validate_integration(manifest: IntegrationManifest) -> IntegrationEvidence:
    checkout = manifest.checkout_path
    if not checkout.is_dir():
        raise IntegrationError(f"checkout does not exist or is not a directory: {checkout}")

    worktree = _git(checkout, "rev-parse", "--is-inside-work-tree")
    if worktree.returncode != 0 or worktree.stdout.strip() != "true":
        raise IntegrationError(f"checkout is not a Git worktree: {checkout}")

    top_level = _git(checkout, "rev-parse", "--show-toplevel")
    observed_top_level = (
        Path(top_level.stdout.strip()).resolve()
        if top_level.returncode == 0 and top_level.stdout.strip()
        else None
    )
    if observed_top_level != checkout.resolve():
        raise IntegrationError(f"checkout is not a Git worktree root: {checkout}")

    failures: list[str] = []
    head = _git(checkout, "rev-parse", "HEAD")
    observed_commit = head.stdout.strip() if head.returncode == 0 else "unavailable"
    if observed_commit != manifest.commit:
        failures.append(
            f"expected commit {manifest.commit}, observed {observed_commit}"
        )

    origin = _git(checkout, "remote", "get-url", "origin")
    observed_origin = origin.stdout.strip() if origin.returncode == 0 else "unavailable"
    if observed_origin != manifest.repository_url:
        failures.append(
            f"unexpected origin URL: expected {manifest.repository_url}, observed {observed_origin}"
        )

    status = _git(checkout, "status", "--porcelain")
    if status.returncode != 0:
        failures.append("unable to determine worktree status")
    elif status.stdout:
        failures.append("worktree is not clean")

    for prohibited_path in manifest.prohibited_paths:
        candidate = checkout / prohibited_path
        if candidate.exists() or candidate.is_symlink():
            failures.append(f"prohibited path is present: {prohibited_path}")

    if failures:
        raise IntegrationError("integration validation failed: " + "; ".join(failures))

    return IntegrationEvidence(
        adapter=manifest.adapter,
        name=manifest.name,
        checkout_path=checkout,
        repository_url=manifest.repository_url,
        commit=manifest.commit,
    )
