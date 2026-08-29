from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


TEST_ORIGIN = "https://example.com/benchmark.git"


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def create_git_repo(parent: Path) -> tuple[Path, str]:
    repo = parent / "Benchmark"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main", str(repo)],
        check=True,
        capture_output=True,
        text=True,
    )
    run_git(repo, "config", "user.name", "Agent Release Gate Tests")
    run_git(repo, "config", "user.email", "tests@example.com")
    (repo / "README.md").write_text("synthetic benchmark\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "test: seed synthetic benchmark")
    run_git(repo, "remote", "add", "origin", TEST_ORIGIN)
    return repo, run_git(repo, "rev-parse", "HEAD")


def write_manifest(
    project_root: Path,
    checkout: Path,
    commit: str,
    *,
    repository_url: str = TEST_ORIGIN,
    prohibited_paths: list[str] | None = None,
    updates: dict[str, object] | None = None,
) -> Path:
    data: dict[str, object] = {
        "schema_version": 1,
        "name": "SyntheticBench",
        "repository_url": repository_url,
        "checkout_path": os.path.relpath(checkout, project_root),
        "commit": commit,
        "prohibited_paths": prohibited_paths or ["vendor"],
    }
    if updates:
        data.update(updates)
    path = project_root / "integration.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
