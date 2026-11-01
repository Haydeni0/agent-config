"""Atomic write primitive shared by the executor and the ownership store.

Lives in its own module (not executor.py as the spec's layout table names)
because ownership importing executor would close an ownership -> executor ->
ownership cycle; the one-line indirection breaks it.
"""

import os
import stat
import tempfile
from pathlib import Path


def write_text_atomic(target: Path, content: str) -> None:
    """Install a complete UTF-8 file, preserving an existing file's mode."""
    if target.is_symlink():
        raise OSError(f"refusing to replace a symlink: {target}")
    mode = stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o600
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
            os.fchmod(file.fileno(), mode)
        if target.is_symlink():
            raise OSError(f"destination became a symlink: {target}")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
