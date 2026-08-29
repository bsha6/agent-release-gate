# Dependencies and Third-Party Boundary

Agent Release Gate has no third-party Python package runtime or test
dependencies. The table below inventories external tools involved in running,
building, verifying, or integrating the project; none are shipped in the wheel.

| Role | Component | Version constraint | License | Distribution boundary |
| --- | --- | --- | --- | --- |
| Runtime | Python standard library | Python 3.14+ | PSF License | Required interpreter; not bundled |
| Runtime and tests | Git CLI | Git 2.x; tests require `git init -b` support | GPL-2.0-only | External provenance tool; not bundled or invoked over a network |
| Tests | `unittest` | Python 3.14+ | PSF License | Standard library; not bundled |
| Build backend | setuptools | `>=80` | MIT | Isolated build dependency; not bundled |
| Build frontend | build | `1.6.0` in CI | MIT | CI/development tool; not bundled |
| CI action | `actions/checkout` | `v7.0.1`, pinned by SHA | MIT | GitHub Actions only |
| CI action | `actions/setup-python` | `v7.0.0`, pinned by SHA | MIT | GitHub Actions only |
| Upstream evidence producer | ClawProBench | commit `c4b8395854fe0752eef435b44f140366efd44d8e` | Apache-2.0 | External read-only checkout; no source vendored |
| Release audit | Gitleaks | Exact release recorded per audit | MIT | Temporary audit tool; not bundled |

License sources:

- Python: <https://docs.python.org/3/license.html>
- Git: <https://github.com/git/git/blob/master/COPYING>
- setuptools: <https://github.com/pypa/setuptools/blob/main/LICENSE>
- build: <https://github.com/pypa/build/blob/main/LICENSE>
- actions/checkout: <https://github.com/actions/checkout/blob/3d3c42e5aac5ba805825da76410c181273ba90b1/LICENSE>
- actions/setup-python: <https://github.com/actions/setup-python/blob/5fda3b95a4ea91299a34e894583c3862153e4b97/LICENSE>
- ClawProBench: <https://github.com/suyoumo/ClawProBench/blob/c4b8395854fe0752eef435b44f140366efd44d8e/LICENSE>
- Gitleaks: <https://github.com/gitleaks/gitleaks/blob/master/LICENSE>

The JSON fixtures under `tests/fixtures/` are original, hand-authored synthetic
data. They contain no copied benchmark results or user data.
