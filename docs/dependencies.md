# Dependencies and Third-Party Boundary

Agent Release Gate has no third-party runtime or test dependencies. The table
below inventories tools involved in building, verifying, or integrating the
project; build and audit tools are not shipped in the wheel.

| Role | Component | Version constraint | License | Distribution boundary |
| --- | --- | --- | --- | --- |
| Runtime | Python standard library | Python 3.14+ | PSF License | Required interpreter; not bundled |
| Tests | `unittest` | Python 3.14+ | PSF License | Standard library; not bundled |
| Build backend | setuptools | `>=80` | MIT | Isolated build dependency; not bundled |
| Build frontend | build | `1.6.0` in CI | MIT | CI/development tool; not bundled |
| CI action | `actions/checkout` | `v7.0.1`, pinned by SHA | MIT | GitHub Actions only |
| CI action | `actions/setup-python` | `v7.0.0`, pinned by SHA | MIT | GitHub Actions only |
| Upstream evidence producer | ClawProBench | commit `c4b8395854fe0752eef435b44f140366efd44d8e` | Apache-2.0 | External read-only checkout; no source vendored |
| Release audit | Gitleaks | Exact release recorded per audit | MIT | Temporary audit tool; not bundled |

License sources:

- Python: <https://docs.python.org/3/license.html>
- setuptools: <https://github.com/pypa/setuptools/blob/main/LICENSE>
- build: <https://github.com/pypa/build/blob/main/LICENSE>
- actions/checkout: <https://github.com/actions/checkout/blob/main/LICENSE>
- actions/setup-python: <https://github.com/actions/setup-python/blob/main/LICENSE>
- ClawProBench: <https://github.com/suyoumo/ClawProBench/blob/main/LICENSE>
- Gitleaks: <https://github.com/gitleaks/gitleaks/blob/master/LICENSE>

The JSON fixtures under `tests/fixtures/` are original, hand-authored synthetic
data. They contain no copied benchmark results or user data.
