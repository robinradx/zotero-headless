from __future__ import annotations

from dataclasses import asdict, dataclass

from .adapters.local_desktop import LocalWriteStrategy, local_write_strategy_note


@dataclass(slots=True)
class ArchitectureState:
    canonical_store: str
    runtime: str
    web_sync: str
    server_mode: str
    desktop_mode: str
    local_desktop_adapter: str
    local_write_strategy: str
    local_write_note: str
    qmd_role: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def current_architecture_state() -> ArchitectureState:
    strategy = LocalWriteStrategy.UNDECIDED
    return ArchitectureState(
        canonical_store="clean-room core",
        runtime="minimal daemon host",
        web_sync="first-class adapter",
        server_mode="core + daemon + web sync",
        desktop_mode="core + optional desktop adapter + web sync",
        local_desktop_adapter="thin interoperability layer",
        local_write_strategy=strategy.value,
        local_write_note=local_write_strategy_note(strategy),
        qmd_role="derived markdown/text index",
    )
