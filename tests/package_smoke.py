from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).parents[1]
ORIGIN = "https://example.com/synthetic-benchmark.git"


def run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def git(repo: Path, *args: str) -> str:
    result = run(
        ["git", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args],
        cwd=repo,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def seed_project(base: Path) -> tuple[Path, Path, Path, Path]:
    project = base / "agent-release-gate"
    checkout = base / "SyntheticBench"
    project.mkdir()
    checkout.mkdir()

    git(checkout, "init", "-b", "main")
    git(checkout, "config", "user.name", "Agent Release Gate CI")
    git(checkout, "config", "user.email", "ci@example.com")
    (checkout / "README.md").write_text("synthetic benchmark\n", encoding="utf-8")
    git(checkout, "add", "README.md")
    git(checkout, "commit", "-m", "test: seed synthetic benchmark")
    git(checkout, "remote", "add", "origin", ORIGIN)
    commit = git(checkout, "rev-parse", "HEAD")

    manifest = project / "integration.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "adapter": "clawprobench",
                "name": "SyntheticBench",
                "repository_url": ORIGIN,
                "checkout_path": "../SyntheticBench",
                "commit": commit,
                "prohibited_paths": ["vendor"],
            }
        ),
        encoding="utf-8",
    )
    policy = project / "policy.toml"
    shutil.copyfile(ROOT / "policies" / "default.toml", policy)
    go_report = project / "go.json"
    no_go_report = project / "no-go.json"
    shutil.copyfile(ROOT / "tests" / "fixtures" / "clawprobench_go.json", go_report)
    shutil.copyfile(
        ROOT / "tests" / "fixtures" / "clawprobench_no_go.json",
        no_go_report,
    )
    return project, manifest, go_report, no_go_report


def evaluate(
    cli: Path,
    project: Path,
    manifest: Path,
    report: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return run(
        [
            str(cli),
            "evaluate",
            "--adapter",
            "clawprobench",
            "--report",
            str(report),
            "--policy",
            str(project / "policy.toml"),
            "--integration",
            str(manifest),
            "--output",
            str(output),
        ],
        cwd=project,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", required=True, type=Path)
    args = parser.parse_args()
    cli = args.cli.resolve(strict=True)

    with tempfile.TemporaryDirectory() as directory:
        project, manifest, go_report, no_go_report = seed_project(Path(directory))
        cases = (
            (go_report, project / "go-decision.json", 0, "go"),
            (no_go_report, project / "no-go-decision.json", 1, "no_go"),
        )
        for report, output, expected_exit, expected_decision in cases:
            result = evaluate(cli, project, manifest, report, output)
            if result.returncode != expected_exit:
                raise RuntimeError(
                    f"{expected_decision} smoke returned {result.returncode}: "
                    f"{result.stderr.strip()}"
                )
            observed = json.loads(output.read_text(encoding="utf-8"))
            if observed["decision"] != expected_decision:
                raise RuntimeError(
                    f"expected {expected_decision}, observed {observed['decision']}"
                )
            if "checkout_path" in observed["integration"]:
                raise RuntimeError("decision leaked the local checkout path")

    print("installed-wheel GO and NO_GO smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
