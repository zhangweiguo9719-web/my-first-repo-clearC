from __future__ import annotations

from pathlib import Path


def send2trash(path: str) -> None:
    """Fallback send2trash implementation for offline/test environments."""
    target = Path(path)
    target.unlink()
