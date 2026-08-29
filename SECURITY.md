# Security Policy

## Supported Versions

Agent Release Gate is an early-stage project. Only the latest `0.1.x` release
is supported with security fixes.

## Reporting a Vulnerability

Use GitHub's **Security** tab and select **Report a vulnerability**. This opens
a private report with the repository owner. Do not disclose suspected
vulnerabilities in a public issue, pull request, discussion, or benchmark
artifact, and do not include credentials, tokens, private data, or exploit data
that is not necessary to reproduce the problem.

If private vulnerability reporting is unavailable, do not publish the details.
Wait until the repository provides a private reporting channel.

Include the affected version or commit, the relevant command and input shape,
the observed impact, and the smallest safe reproduction. Redact personal data
and secrets.

Reports are acknowledged and handled on a best-effort basis. No response or
remediation timeline is guaranteed for this early release.

## Scope

Security reports may cover the CLI, report and policy parsing, integration
provenance checks, output-path handling, packaging, and CI configuration.
ClawProBench is an independent upstream project; report vulnerabilities in its
code to its maintainers.
