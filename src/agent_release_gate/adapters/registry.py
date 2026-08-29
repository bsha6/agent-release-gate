from __future__ import annotations

from types import MappingProxyType
from collections.abc import Mapping

from agent_release_gate.adapters.base import BenchmarkAdapter, ReportError
from agent_release_gate.adapters.clawprobench import ClawProBenchAdapter


_ADAPTERS: Mapping[str, BenchmarkAdapter] = MappingProxyType(
    {"clawprobench": ClawProBenchAdapter()}
)


def adapter_names() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def get_adapter(name: str) -> BenchmarkAdapter:
    try:
        return _ADAPTERS[name]
    except KeyError as exc:
        available = ", ".join(adapter_names())
        raise ReportError(f"unknown adapter {name!r}; available: {available}") from exc
