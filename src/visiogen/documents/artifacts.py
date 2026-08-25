"""Atomic publication of a complete deterministic document snapshot bundle."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Callable

from visiogen.documents.errors import UnsafeDocumentError


StageBuilder = Callable[[Path], object]


def publish_artifact_directory(destination: str | Path, build: StageBuilder) -> object:
    """Build in a private sibling and atomically publish into an absent/empty path."""

    output = Path(destination)
    if output.is_symlink():
        raise UnsafeDocumentError("Artifact directory must not be a symbolic link")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise UnsafeDocumentError("Artifact directory must be absent or empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output.name}.", dir=output.parent) as temporary:
        stage = Path(temporary) / "bundle"
        stage.mkdir(mode=0o700)
        result = build(stage)
        if output.exists():
            output.rmdir()
        stage.replace(output)
    return result
