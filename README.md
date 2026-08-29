# Agent Release Gate

Agent Release Gate turns completed agent-benchmark evidence into a deterministic `go` or `no_go` decision. The v0 release supports ClawProBench through a benchmark adapter while keeping gate policy and decision logic independent of that benchmark.

The tool reads existing JSON reports. It does not install, import, execute, fetch, or modify ClawProBench.

## Requirements

- Python 3.14 or newer; development is verified with `python3.14`.
- Git, used only for read-only provenance checks.
- The audited ClawProBench checkout at `../ClawProBench`.

No package installation is needed for repository development. Prefix commands with `PYTHONPATH=src`.

## Validate the Integration

```bash
PYTHONPATH=src python3.14 -m agent_release_gate doctor
```

`doctor` validates the checkout, origin URL, audited commit, clean worktree, and absence of prohibited vendored directories. It never runs upstream code.

## Evaluate a Report

```bash
mkdir -p decisions
PYTHONPATH=src python3.14 -m agent_release_gate evaluate \
  --adapter clawprobench \
  --report /path/to/result.json \
  --policy policies/default.toml \
  --output decisions/release-decision.json
```

The output is written atomically. A failed evaluation leaves an existing output file unchanged.

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
- `docs/architecture.md`: system boundaries and data flow.
- `docs/adding-an-adapter.md`: extension contract for another agent benchmark.

## Audited ClawProBench Boundary

The v0 manifest pins:

- repository: `https://github.com/suyoumo/ClawProBench.git`;
- commit: `c4b8395854fe0752eef435b44f140366efd44d8e`;
- checkout: sibling directory `../ClawProBench`;
- prohibited checked-out paths: `ironclaw` and `nanoclaw`.

Generated benchmark reports are inputs to this repository. ClawProBench remains a read-only upstream dependency.
