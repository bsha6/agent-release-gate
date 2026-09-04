# Agent Release Gate

[![CI](https://github.com/bsha6/agent-release-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/bsha6/agent-release-gate/actions/workflows/ci.yml)
![Python 3.14+](https://img.shields.io/badge/Python-3.14%2B-3776AB)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)

Agent Release Gate turns a completed agent-benchmark report into a deterministic,
machine-readable `go` or `no_go` decision. It is designed for release automation
that needs an explicit answer after evaluation: **does this agent version satisfy
this release policy?**

The v0 adapter reads [ClawProBench](https://github.com/suyoumo/ClawProBench)
reports. The gate does not fetch, install, import, or execute benchmark code.

## Why use a release gate?

A benchmark score is evidence, not a release policy. Agent Release Gate keeps
those concerns separate:

- a benchmark produces a report;
- an adapter validates and normalizes that report;
- a versioned TOML policy defines acceptable capability, reliability, coverage,
  safety, and execution integrity;
- the evaluator applies every rule in a stable order;
- the CLI writes a decision artifact and returns an automation-friendly exit
  code.

```text
benchmark report ──> adapter ──> normalized evidence ──┐
                                                       ├──> evaluator ──> decision JSON
policy TOML ───────────────────────────────────────────┘                 + exit code

pinned benchmark checkout ──> provenance validation ────────────────────┘
```

The result records the report hash, policy hash, benchmark source commit,
observed metrics, and every blocking rule. Except for `evaluated_at`, equivalent
inputs produce equivalent substantive output.

## Quickstart

### 1. Create the expected checkout layout

The project and audited benchmark checkout must be direct siblings:

```text
Projects/
├── agent-release-gate/
└── ClawProBench/
```

Clone ClawProBench without running hooks or checking out its vendored agent
implementations:

```bash
cd /path/to/Projects
git clone \
  --filter=blob:none \
  --no-checkout \
  --no-recurse-submodules \
  -c core.hooksPath=/dev/null \
  https://github.com/suyoumo/ClawProBench.git ClawProBench
cd ClawProBench
git sparse-checkout init --cone
git sparse-checkout set \
  config custom_checks datasets fixtures frameworks harness \
  mock_tools scenarios scripts tests
git -c core.hooksPath=/dev/null checkout --detach \
  c4b8395854fe0752eef435b44f140366efd44d8e
```

The default integration manifest requires that exact origin and commit, a clean
worktree, and no checked-out `ironclaw/` or `nanoclaw/` directories.

### 2. Install the CLI

Agent Release Gate is not published to PyPI. From a trusted source checkout:

```bash
cd /path/to/Projects/agent-release-gate
python3.14 -m venv .venv
.venv/bin/python -m pip install .
```

Requirements are Python 3.14+, Git, and a POSIX-style operating system with
descriptor-relative filesystem operations. The installed package has no
third-party runtime dependencies. Run commands from the source checkout when
using the included default policy and integration manifest.

### 3. Verify benchmark provenance

```bash
.venv/bin/agent-release-gate doctor
```

A valid checkout produces JSON and exits `0`:

```json
{
  "integration": {
    "adapter": "clawprobench",
    "commit": "c4b8395854fe0752eef435b44f140366efd44d8e",
    "name": "ClawProBench",
    "repository_url": "https://github.com/suyoumo/ClawProBench.git"
  },
  "schema_version": 1,
  "valid": true
}
```

`doctor` uses read-only Git commands. It never runs upstream code or changes the
benchmark checkout.

### 4. Evaluate an existing report

```bash
mkdir -p decisions
.venv/bin/agent-release-gate evaluate \
  --adapter clawprobench \
  --report tests/fixtures/clawprobench_go.json \
  --policy policies/default.toml \
  --integration integrations/clawprobench.lock.json \
  --output decisions/release-decision.json
```

An abridged passing decision looks like this:

```json
{
  "adapter": "clawprobench",
  "decision": "go",
  "blockers": [],
  "benchmark": {
    "name": "ClawProBench",
    "source_version": "c4b8395854fe0752eef435b44f140366efd44d8e",
    "subject": "agent-go"
  },
  "observed": {
    "capability_score": 0.8,
    "coverage_ratio": 1.0,
    "execution_failures": 0,
    "safety_passed": true,
    "strict_pass_rate": 0.8
  },
  "policy": {
    "name": "default",
    "min_capability_score": 0.7,
    "min_coverage_ratio": 1.0,
    "min_strict_pass_rate": 0.7
  },
  "schema_version": 1
}
```

The committed fixtures are synthetic examples, not copied benchmark results or
user data.

## Automation contract

Consumers should use both the exit code and decision artifact:

- `0`: valid evaluation with decision `go`;
- `1`: valid evaluation with decision `no_go`;
- `2`: invalid arguments, unproven integration, malformed evidence, invalid
  policy, unknown adapter, or output failure.

Treat exit `2` as a pipeline error, not as an ordinary failed release gate:

```bash
gate_status=0
agent-release-gate evaluate \
  --adapter clawprobench \
  --report "$REPORT_PATH" \
  --policy policies/default.toml \
  --integration integrations/clawprobench.lock.json \
  --output release-decision.json || gate_status=$?

case "$gate_status" in
  0) echo "release approved" ;;
  1) echo "release blocked"; exit 1 ;;
  2) echo "release evaluation invalid" >&2; exit 2 ;;
esac
```

The CLI evaluates every policy rule, so a `no_go` decision reports all observed
blockers rather than stopping at the first failure. If evaluation fails before a
valid decision is produced, an existing output file is preserved.

## Input and output contracts

### Report

The ClawProBench adapter accepts an existing JSON report and validates required
field types, numeric ranges, scenario counts, per-trial safety state, and
execution status. Unknown additive fields are ignored. The exact report bytes
are hashed with SHA-256 and recorded in the decision.

The report is evidence supplied to the gate. v0 does not prove that it was
produced honestly or by the pinned benchmark source.

### Policy

The default [`[gate]` policy](policies/default.toml) requires:

- capability score of at least `0.70`;
- strict pass rate of at least `0.70`;
- complete requested-scenario coverage;
- every observed trial to pass its safety gate;
- zero execution failures.

A custom TOML policy can change thresholds without changing the adapter or
evaluation logic. The exact policy bytes are hashed into the decision.

### Integration manifest

The [ClawProBench lock file](integrations/clawprobench.lock.json) binds an adapter
to its expected repository URL, full Git commit, sibling checkout path, and
prohibited checked-out paths. Evaluation fails before reading the report if the
requested adapter and manifest do not match.

### Decision

The output is sorted, indented JSON containing:

- `go` or `no_go` and ordered blockers;
- normalized observed metrics;
- benchmark identity, report hash, and report timestamp;
- policy values and policy hash;
- validated repository URL and source commit;
- schema version and UTC evaluation time.

Absolute local checkout paths are never serialized. Output must be separate
from the report, policy, manifest, and benchmark checkout.

## Safety boundary

Inputs and the validated benchmark checkout are pinned by file descriptor.
Output is written atomically through a held directory descriptor. The CLI
defends against path replacement, parent-symlink swaps, case variants, hard-link
aliases, mixed-checkout provenance, hidden untracked files, and Git index flags
that can conceal modifications.

Filesystem identity and ancestry are checked when descriptors are acquired and
immediately before output commit. A hostile concurrent process that can write
both the output and benchmark directory trees is outside the v0 threat model;
run evaluations where untrusted processes cannot rename those directories.

See [architecture](docs/architecture.md), [dependency boundaries](docs/dependencies.md),
and the [security policy](SECURITY.md) for the detailed model.

## Adding another benchmark

Benchmark-specific parsing stops at the adapter boundary. The domain model,
policy evaluator, decision schema, and exit-code contract do not depend on
ClawProBench.

To add a benchmark:

1. implement the `BenchmarkAdapter` protocol;
2. normalize its report into `BenchmarkEvidence`;
3. register one stable lowercase adapter name;
4. add a pinned integration manifest;
5. cover passing, blocking, malformed, and additive report cases with synthetic
   fixtures.

See [Adding a Benchmark Adapter](docs/adding-an-adapter.md) for the full
contract.

## Development

No dependency installation is required for repository tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3.14 -m unittest discover -s tests -v
```

CI runs the full suite and installed-package smoke tests on macOS and Ubuntu. It
also builds the wheel and a source archive with neutral ownership metadata.

## Project status

Version `0.1.0` is an early, source-distributed release supporting the documented
ClawProBench report shape and integration. Outside pull requests and feature
requests are not being solicited for v0.

Agent Release Gate is licensed under the [Apache License 2.0](LICENSE). Report
vulnerabilities through the private process in [SECURITY.md](SECURITY.md).
