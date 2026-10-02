"""Keep verified extra library copies without overwriting existing songs."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from src.services.library_scanner import file_sha256
from src.utils.filesystem import ensure_within


def sync_library_copies(
    source: Path,
    primary: Path,
    destinations: list[Path],
    *,
    source_roots: list[Path] | None = None,
) -> list[Path]:
    """Also retry songs downloaded to an earlier configured NAS primary folder."""
    roots = [primary, *destinations]
    for root in [*roots, *(source_roots or [])]:
        if source.resolve().is_relative_to(root.resolve()):
            return copy_to_libraries(source, root, roots)
    msg = f"Song is outside the configured library folders: {source}"
    raise ValueError(msg)


def copy_to_libraries(source: Path, primary: Path, destinations: list[Path]) -> list[Path]:
    """Copy a finalized tagged song; an unavailable destination is a visible error."""
    relative = ensure_within(primary, source).relative_to(primary.resolve())
    copied = []
    for root in destinations:
        if root.resolve() == primary.resolve():
            continue
        # Do not create a missing mount/share as a misleading local directory.
        if not root.is_dir():
            msg = f"Copy folder unavailable: {root}. Local song retained at {source}; retry later."
            raise OSError(msg)
        target = root / relative
        ensure_within(root, target)
        target.parent.mkdir(parents=True, exist_ok=True)
        ensure_within(root, target)
        verified_copy(source, target)
        copied.append(target)
    return copied


def verified_copy(source: Path, target: Path) -> Path:
    """Atomically publish a verified copy, retaining every existing song."""
    digest = file_sha256(source)
    if target.exists():
        if file_sha256(target) != digest:
            msg = f"Existing copy differs: {target}; both songs retained, nothing overwritten."
            raise FileExistsError(msg)
        return target
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".partial", delete=False) as out:
            temporary = Path(out.name)
            with source.open("rb") as original:
                shutil.copyfileobj(original, out)
            out.flush()
            os.fsync(out.fileno())
        if file_sha256(temporary) != digest:
            msg = f"Copy verification failed: {target}; local song retained."
            raise OSError(msg)
        if os.name == "nt":
            temporary.rename(target)  # atomic; refuses to replace an existing file
        else:
            os.link(temporary, target)  # POSIX rename would overwrite
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)  # only our regenerable partial
