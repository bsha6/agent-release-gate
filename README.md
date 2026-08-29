# Agent Release Gate

Agent Release Gate turns completed agent-benchmark evidence into a deterministic `go` or `no_go` decision. The v0 release supports ClawProBench through a benchmark adapter while keeping gate policy and decision logic independent of that benchmark.

The tool reads existing JSON reports. It does not install, import, execute, fetch, or modify ClawProBench.

## Status

Version `0.1.0` is an early, source-distributed release. The public repository
is intended for inspection and use, but outside pull requests and feature
requests are not being solicited for v0.

## Installation

Agent Release Gate is not published to PyPI. Install it from a trusted source
checkout:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/agent-release-gate --help
```

To install a wheel produced from the checkout:

```bash
uv build
python3.14 -m venv /tmp/agent-release-gate
/tmp/agent-release-gate/bin/python -m pip install \
  dist/agent_release_gate-0.1.0-py3-none-any.whl
/tmp/agent-release-gate/bin/agent-release-gate --help
```

## Requirements

- Python 3.14 or newer; development is verified with `python3.14`.
- A POSIX-style operating system with descriptor-relative filesystem operations;
  v0 is verified on macOS and Linux.
- Git, used only for read-only provenance checks.
- The audited ClawProBench checkout at `../ClawProBench`.

No package installation is needed for repository development. Prefix commands with `PYTHONPATH=src`.

## Validate the Integration

```bash
PYTHONPATH=src python3.14 -m agent_release_gate doctor
```

`doctor` pins and validates the checkout, origin URL, audited commit, clean
worktree, and absence of prohibited vendored directories. It never runs
upstream code.

## Evaluate a Report

```bash
mkdir -p decisions
PYTHONPATH=src python3.14 -m agent_release_gate evaluate \
  --adapter clawprobench \
  --report /path/to/result.json \
  --policy policies/default.toml \
  --output decisions/release-decision.json
```

Evaluation inputs and the validated benchmark checkout are pinned by file
descriptor, and output is written atomically through a held directory
descriptor. A failed evaluation leaves an existing output file unchanged;
concurrent path or parent-symlink swaps cannot substitute an input, mix
checkout provenance, redirect the write into the checkout, or overwrite a
protected input through a case-variant or hard-link alias.

Exit codes are:

- `0`: valid evaluation with decision `go`;
- `1`: valid evaluation with decision `no_go`;
- `2`: invalid arguments, integration, policy, report, adapter, or output operation.

## Default Policy

The `[gate]` table in `policies/default.toml` requires:

- capability score of at least `0.70`;
- strict pass rate of at least `0.70`;
- complete requested-scenario coverage;
- every observed trial to pass its safety gate;
- zero execution failures.

All failed rules are returned as ordered blockers. A custom policy can change these thresholds without changing benchmark adapters or evaluation code.

## Development

Run the complete suite:

```bash
PYTHONPATH=src python3.14 -m unittest discover -s tests -v
```

Run one test:

```bash
PYTHONPATH=src python3.14 -m unittest \
  tests.test_evaluator.EvaluateTests.test_all_thresholds_met_returns_go -v
```

Inspect CLI help:

```bash
PYTHONPATH=src python3.14 -m agent_release_gate --help
PYTHONPATH=src python3.14 -m agent_release_gate doctor --help
PYTHONPATH=src python3.14 -m agent_release_gate evaluate --help
```

Tests use synthetic JSON and disposable Git repositories. They do not execute the upstream benchmark.

## Repository Map

- `src/agent_release_gate/adapters/`: benchmark-specific normalization.
- `src/agent_release_gate/domain/`: benchmark-neutral evidence and policy models.
- `src/agent_release_gate/evaluation/`: pure deterministic gate rules.
- `src/agent_release_gate/integration/`: pinned source validation.
- `integrations/`: audited benchmark manifests.
- `policies/`: release threshold policies.
- `tests/`: synthetic fixtures and behavior tests.
- `tools/`: release-artifact metadata normalization.
- `docs/architecture.md`: system boundaries and data flow.
- `docs/adding-an-adapter.md`: extension contract for another agent benchmark.

## Audited ClawProBench Boundary

The v0 manifest pins:

- repository: `https://github.com/suyoumo/ClawProBench.git`;
- commit: `c4b8395854fe0752eef435b44f140366efd44d8e`;
- checkout: sibling directory `../ClawProBench`;
- prohibited checked-out paths: `ironclaw` and `nanoclaw`.

Generated benchmark reports are inputs to this repository. ClawProBench remains a read-only upstream dependency.

ClawProBench is licensed under Apache-2.0. Agent Release Gate does not vendor,
modify, or redistribute its source. See [dependency boundaries](docs/dependencies.md)
for the complete build, test, CI, upstream, and audit inventory.

## Trust Model and Limitations

- The CLI evaluates supplied reports; it does not prove that a report was
  produced honestly or by the pinned benchmark source.
- v0 preserves the report timestamp but does not enforce evidence freshness.
- Custom policies and integration manifests are trusted local configuration.
- The CLI does not fetch or execute benchmark code.
- Decision output must be separate from reports, policies, manifests, and
  benchmark checkouts; protected paths are rejected after symlink resolution
  while input files, the benchmark checkout, and the output directory remain
  pinned by descriptor.
- The source distribution includes the default policy and integration manifest.
  A standalone wheel contains only the CLI package, so invoke it from a source
  checkout or pass explicit `--policy` and `--integration` paths.
- v0 supports only the documented ClawProBench report shape and default
  integration. Unknown additive report fields are tolerated.
- A deterministic `go` means only that the supplied evidence satisfies the
  supplied policy. It is not a general security certification.

Serialized decisions include the pinned repository URL and commit but omit the
absolute local checkout path to avoid leaking machine-specific information.

## Security and License

Report vulnerabilities through the private process in [SECURITY.md](SECURITY.md).
Agent Release Gate is licensed under the [Apache License 2.0](LICENSE).
