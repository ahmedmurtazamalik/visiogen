"""Tests for atomic document-analysis bundle publication."""

from pathlib import Path

import pytest

from visiogen.documents.artifacts import publish_artifact_directory
from visiogen.documents.errors import UnsafeDocumentError


def test_publish_artifact_directory_replaces_empty_destination_atomically(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    output.mkdir()

    result = publish_artifact_directory(
        output,
        lambda stage: ((stage / "complete.txt").write_text("complete"), "ok")[1],
    )

    assert result == "ok"
    assert (output / "complete.txt").read_text() == "complete"


def test_publish_artifact_directory_preserves_empty_destination_on_failure(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    output.mkdir()

    def fail(stage: Path) -> None:
        (stage / "partial.txt").write_text("partial")
        raise RuntimeError("failed")

    with pytest.raises(RuntimeError, match="failed"):
        publish_artifact_directory(output, fail)

    assert output.is_dir()
    assert list(output.iterdir()) == []


def test_publish_artifact_directory_rejects_nonempty_destination(tmp_path: Path) -> None:
    output = tmp_path / "evidence"
    output.mkdir()
    (output / "owned.txt").write_text("keep")

    with pytest.raises(UnsafeDocumentError, match="absent or empty"):
        publish_artifact_directory(output, lambda stage: None)

    assert (output / "owned.txt").read_text() == "keep"
