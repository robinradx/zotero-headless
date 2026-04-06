from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class RuntimeMode:
    name: str
    description: str
    requires_desktop_zotero: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def server_runtime_mode() -> RuntimeMode:
    return RuntimeMode(
        name="server",
        description="Clean-room core hosted by zotero-headless-daemon with web sync and no Zotero desktop dependency.",
        requires_desktop_zotero=False,
    )


def desktop_runtime_mode() -> RuntimeMode:
    return RuntimeMode(
        name="desktop",
        description="Clean-room core running on an end-user machine with optional Zotero desktop interoperability.",
        requires_desktop_zotero=False,
    )
