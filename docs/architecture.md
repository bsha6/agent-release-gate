# Architecture

## Purpose and Boundary

Agent Release Gate decides whether completed agent-benchmark evidence satisfies a release policy. It deliberately separates evidence production from evidence evaluation: benchmark runners produce reports elsewhere, while this project reads those reports and makes a reproducible decision.

ClawProBench is a read-only upstream dependency. The application never imports its Python modules, runs its scripts, installs its requirements, or changes its checkout.

## Dependency Direction

The domain and evaluator form the stable center:

```text
CLI ──> integration validator
 │
 ├──> adapter registry ──> benchmark adapter ──> domain evidence
 │
 └──> policy loader ───────────────────────────> evaluator ──> decision
```

- Domain models know only normalized benchmark identity, metrics, policy, blockers, and decisions.
- The evaluator is a pure function and has no filesystem, Git, CLI, or benchmark dependency.
- Adapters depend on the domain model and translate one external report schema.
- Integration validation proves benchmark source provenance using read-only Git commands.
- The CLI coordinates these units, adds provenance and policy digests, and atomically writes JSON.

This direction lets another agent benchmark reuse the same policies, evaluator, output semantics, and exit codes.

## Data Flow

For `doctor`:

1. Load and strictly validate the integration manifest.
2. Bind the manifest's declared adapter to the registry key used for evaluation.
3. Resolve its checkout as a direct sibling of this repository.
4. Verify Git worktree state, `HEAD`, `origin`, cleanliness, and prohibited paths.
5. Emit validated provenance as JSON without the absolute local checkout path.

For `evaluate`:

1. Perform the same integration validation.
2. Select the named benchmark adapter and require it to match the manifest.
3. Open and validate the output directory, rejecting benchmark-checkout or
   input-file targets while holding the directory descriptor through the write.
4. Validate and normalize the report into `BenchmarkEvidence`.
5. Parse and validate the TOML policy, retaining its SHA-256 digest.
6. Apply every gate rule in stable order.
7. Combine decision, observed metrics, report identity, integration provenance, policy identity, and UTC evaluation time.
8. Write sorted, indented JSON to a sibling temporary file, sync it, and replace the target atomically.

Input errors are distinct from release outcomes. A valid `no_go` is exit code `1`; malformed evidence or unproven provenance is exit code `2` and produces no decision.

## Normalized Evidence

The evaluator consumes only:

- benchmark and report identity;
- capability score;
- strict pass rate;
- completed and requested scenario counts;
- aggregate safety status;
- execution-failure count.

ClawProBench-specific nesting and field validation stop at the adapter boundary. Unknown extra report fields are tolerated so additive upstream changes do not break the gate; missing required fields or inconsistent counts are rejected.

## Policy Evaluation

The default rules evaluate capability, strict reliability, coverage, safety, and execution integrity. Every rule runs even after one fails, allowing a single decision to explain all blockers. Rule order is fixed so equivalent inputs produce equivalent substantive output.

The evaluation timestamp is the only time-varying output field. Tests inject a clock.

## Provenance and Safety

The integration manifest pins the expected origin and full Git commit. Validation uses only:

- `git rev-parse --is-inside-work-tree`;
- `git rev-parse --show-toplevel`;
- `git rev-parse HEAD`;
- `git remote get-url origin`;
- `git status --porcelain`.

Git hooks and fsmonitor are disabled for these read-only subprocesses, terminal prompts are disabled, and `GIT_OPTIONAL_LOCKS=0` prevents status checks from refreshing the upstream index. The validator also disables Git's untracked cache, ignores global/system Git configuration, and removes inherited `GIT_*` variables before setting its explicit safe environment. This prevents ambient `GIT_DIR`, `GIT_WORK_TREE`, or index overrides from redirecting a probe away from the pinned checkout. Validation never fetches, checks out, resets, cleans, or writes upstream files.

The integration manifest declares the adapter that may consume its evidence.
This prevents a CLI invocation from presenting one benchmark's source
provenance alongside a different adapter. Prohibited paths are detected even
when represented by dangling symlinks.

Before reading evaluation inputs, the CLI resolves the requested output path,
opens its directory without following the final path component, and verifies
the opened directory by device and inode. It rejects paths inside the benchmark
checkout and paths equal to the report, policy, or integration manifest,
including aliases reached through symlinked parents. The same directory
descriptor is used to create and replace the decision file, so a concurrent
symlink-parent swap cannot redirect the write. The resolved checkout stays
internal and is not serialized.

## Failure Handling

Expected input and filesystem failures produce a concise stderr message without a traceback. Atomic output prevents a failed evaluation from truncating a previous decision. Unexpected failures are contained at the command boundary and return exit code `2`.
