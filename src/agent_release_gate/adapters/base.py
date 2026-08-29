from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agent_release_gate.domain.models import BenchmarkEvidence


class ReportError(ValueError):
    """Raised when a benchmark report cannot be normalized safely."""


class BenchmarkAdapter(Protocol):
    def load(self, report_path: Path, *, source_version: str) -> BenchmarkEvidence:
        """Validate and normalize one benchmark report."""
