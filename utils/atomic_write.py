"""Atomic file writes for all pipeline exports.

Readers (the Apache static server and through it the mastr-app) must never
observe a partially written export file. Every export is therefore written
to a hidden temporary file in the target directory and moved into place
with os.replace(), which is an atomic rename on POSIX: readers see either
the complete old file or the complete new file, never anything in between.

The temporary file must live in the same directory as the target so that
the rename stays on one filesystem.
"""

import os
import uuid
from pathlib import Path
from typing import Callable

# marker for temporary files of crashed runs, swept at the start of the
# next export (the pipeline is single-writer: one run at a time)
TEMP_MARKER = ".tmp-"


def temp_path_for(target: Path) -> Path:
    """Unique hidden temporary path next to the target file.

    The pid-uuid suffix makes collisions impossible, even between parallel
    export workers writing different files in the same directory.
    """
    return target.with_name(f".{target.name}{TEMP_MARKER}{os.getpid()}-{uuid.uuid4().hex[:8]}")


def atomic_write(target: Path, writer: Callable[[Path], None]) -> None:
    """Write a file atomically: writer fills the temporary file, then it is
    renamed to the target.

    If the writer fails, the temporary file is removed and the previous
    target file (if any) stays untouched.
    """
    temp = temp_path_for(target)
    try:
        writer(temp)
        os.replace(temp, target)
    except BaseException:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def cleanup_stale_temp_files(directory: Path) -> int:
    """Remove leftover temporary files of crashed runs and return their count.

    Only hidden files carrying the temp marker are removed; regular export
    files are never touched. Safe under the pipeline's single-writer
    contract - no other export run is active when this is called.
    """
    removed = 0
    if not directory.is_dir():
        return removed
    for path in directory.iterdir():
        if path.is_file() and path.name.startswith(".") and TEMP_MARKER in path.name:
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    return removed
