# Adding a Benchmark Adapter

An adapter translates one agent benchmark's report into the small evidence model consumed by the evaluator. It must not run the benchmark or embed release-policy decisions.

## Contract

Implement the `BenchmarkAdapter` protocol from `agent_release_gate.adapters.base`:

```python
def load(
    self,
    report_path: Path,
    *,
    source_version: str,
) -> BenchmarkEvidence:
    ...
```

The adapter must:

- read the report without changing it;
- validate required types, numeric ranges, and internal counts;
- reject non-finite numeric values;
- raise `ReportError` with a useful field path for invalid input;
- hash the exact report bytes with SHA-256;
- preserve the supplied `source_version` in `BenchmarkIdentity`;
- return normalized capability, strict pass rate, coverage counts, safety status, and execution failures;
- ignore unknown additive fields that do not change required semantics.

Do not import benchmark implementation modules. The report schema is the integration boundary.

## Registration

Add one stable lowercase name to the immutable registry in `adapters/registry.py`. Do not add benchmark branches to the evaluator or CLI.

For example:

```python
_ADAPTERS = MappingProxyType(
    {
        "clawprobench": ClawProBenchAdapter(),
        "otherbench": OtherBenchAdapter(),
    }
)
```

## Provenance

Add a strict manifest under `integrations/` for the benchmark source. The manifest identifies the source repository, audited version, expected local checkout, and prohibited paths. Adapter code receives the validated source version; it does not perform Git operations itself.

The manifest's `adapter` field must exactly match the lowercase registry key.
Evaluation rejects a different `--adapter` value before reading a report or
writing a decision. Keep the checkout as a direct sibling, and never use a
decision output path inside that checkout.

## Tests

Start with synthetic, hand-checked reports. Tests must cover:

- one valid passing report;
- one valid report that produces every relevant blocker;
- missing required fields and incorrect types;
- booleans used where JSON numbers are expected;
- non-finite and out-of-range metrics;
- inconsistent scenario and trial counts;
- safety and execution-failure normalization;
- ignored unknown fields;
- registry selection and unknown adapter errors.

Use disposable repositories for provenance tests. Never execute or mutate the real benchmark checkout in automated tests.
