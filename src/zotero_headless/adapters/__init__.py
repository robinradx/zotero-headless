from .local_desktop import (
    LocalDesktopAdapter,
    LocalDesktopCapabilities,
    LocalWriteStrategy,
    local_write_strategy_note,
)
from .web_sync import WebLibraryCursor, WebSyncAdapter, WebSyncCapabilities

__all__ = [
    "LocalDesktopAdapter",
    "LocalDesktopCapabilities",
    "LocalWriteStrategy",
    "WebLibraryCursor",
    "WebSyncAdapter",
    "WebSyncCapabilities",
    "local_write_strategy_note",
]
