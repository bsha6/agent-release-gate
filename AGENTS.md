# Agent Release Gate guidance

This repository evaluates completed benchmark evidence. It does not run the
benchmark that produced that evidence. Start with [README.md](README.md); see
[docs/architecture.md](docs/architecture.md) for the trust boundary.

## Operating the gate

- **Validate provenance first.** Run `agent-release-gate doctor` and stop if it
  exits nonzero. Exit `0` confirms provenance only; it is not release approval.
  Do not evaluate evidence against an unproven integration.
- **Keep ClawProBench read-only.** Never install, import, execute, fetch, reset,
  clean, or modify its checkout. The default integration expects a clean
  checkout at `../ClawProBench` on commit
  `c4b8395854fe0752eef435b44f140366efd44d8e`, without `ironclaw/` or
  `nanoclaw/` checked out.
- **Treat reports as immutable evidence.** Do not fabricate, repair, or rewrite
  a benchmark report to make a gate pass. Invalid evidence is an evaluation
  error, not a release result.
- **Interpret `evaluate` exit codes exactly.** Exit `0` is `go`, exit `1` is a
  valid `no_go`, and exit `2` means the evaluation itself is invalid. Do not
  collapse exit `1` and exit `2` into the same outcome.
- **Read the decision artifact.** Report every blocker from the generated JSON;
  do not infer success merely because an output file already exists.
- **Keep output separate.** Never place a decision inside the benchmark
  checkout or overwrite the report, policy, or integration manifest.
- **Resolve configuration deliberately.** Run from the source checkout when
  using the included default policy and integration manifest. Otherwise pass
  explicit `--policy` and `--integration` paths.
