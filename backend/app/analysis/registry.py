"""Explicit registry for analysis modules."""

from __future__ import annotations

from collections.abc import Iterable

from app.analysis.contracts import AnalysisModule


class AnalysisModuleRegistry:
    """Keep module discovery deterministic and reject duplicate module names."""

    def __init__(self, modules: Iterable[AnalysisModule] = ()) -> None:
        self._modules: dict[str, AnalysisModule] = {}
        for module in modules:
            self.register(module)

    def register(self, module: AnalysisModule) -> None:
        if not isinstance(module, AnalysisModule):
            raise TypeError(
                "analysis modules must implement the AnalysisModule protocol"
            )
        if module.name in self._modules:
            raise ValueError(f"analysis module {module.name!r} is already registered")
        self._modules[module.name] = module

    def get(self, name: str) -> AnalysisModule:
        try:
            return self._modules[name]
        except KeyError as exc:
            raise KeyError(f"analysis module {name!r} is not registered") from exc

    def modules(self) -> tuple[AnalysisModule, ...]:
        """Return modules in stable registration order for sequential execution."""
        return tuple(self._modules.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._modules)
