import subprocess
from pathlib import Path

import pytest

from visiogen.preview import PreviewError, export_vsdx_preview


class FakeRunner:
    def __init__(self, *, returncode: int = 0, produce_output: bool = True) -> None:
        self.calls = []
        self.returncode = returncode
        self.produce_output = produce_output
        self.script_text = ""

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        self.script_text = Path(args[5]).read_text()
        if self.returncode == 0 and self.produce_output:
            Path(args[-1]).write_bytes(b"visio-png")
        return subprocess.CompletedProcess(
            args,
            self.returncode,
            stdout="ok" if self.returncode == 0 else "",
            stderr="" if self.returncode == 0 else "failed",
        )


def test_export_preview_uses_microsoft_visio_com(tmp_path: Path) -> None:
    source = tmp_path / "drawing.vsdx"
    source.write_bytes(b"vsdx")
    destination = tmp_path / "preview.png"
    runner = FakeRunner()

    result = export_vsdx_preview(
        source,
        destination,
        runner=runner,
        platform_name="nt",
        powershell_command="powershell.exe",
    )

    assert result == destination
    assert destination.read_bytes() == b"visio-png"
    assert len(runner.calls) == 1
    args, kwargs = runner.calls[0]
    assert args[:5] == [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Sta",
        "-File",
    ]
    script = runner.script_text
    assert "New-Object -ComObject Visio.Application" in script
    assert "OpenEx($SourcePath, 2)" in script
    assert "$page.Export($DestinationPath)" in script
    assert args[-2] == str(source.resolve())
    assert Path(args[-1]).name == "visio-export.png"
    assert Path(args[-1]).parent != destination.parent
    assert kwargs["timeout"] == 120


def test_export_preview_requires_windows_and_visio(tmp_path: Path) -> None:
    source = tmp_path / "drawing.vsdx"
    source.write_bytes(b"vsdx")

    with pytest.raises(PreviewError, match="Microsoft Visio.*Windows"):
        export_vsdx_preview(
            source,
            tmp_path / "preview.png",
            runner=FakeRunner(),
            platform_name="posix",
        )


def test_export_preview_surfaces_visio_failure(tmp_path: Path) -> None:
    source = tmp_path / "drawing.vsdx"
    source.write_bytes(b"vsdx")

    with pytest.raises(PreviewError, match="Microsoft Visio preview export failed"):
        export_vsdx_preview(
            source,
            tmp_path / "preview.png",
            runner=FakeRunner(returncode=2),
            platform_name="nt",
        )


def test_export_preview_requires_exported_png(tmp_path: Path) -> None:
    source = tmp_path / "drawing.vsdx"
    source.write_bytes(b"vsdx")

    with pytest.raises(PreviewError, match="did not produce"):
        export_vsdx_preview(
            source,
            tmp_path / "preview.png",
            runner=FakeRunner(produce_output=False),
            platform_name="nt",
        )


def test_export_preview_rejects_symlink_destination(tmp_path: Path) -> None:
    source = tmp_path / "drawing.vsdx"
    source.write_bytes(b"vsdx")
    victim = tmp_path / "victim.png"
    victim.write_bytes(b"keep")
    destination = tmp_path / "preview.png"
    destination.symlink_to(victim)

    with pytest.raises(PreviewError, match="must not already exist"):
        export_vsdx_preview(
            source,
            destination,
            runner=FakeRunner(),
            platform_name="nt",
        )

    assert victim.read_bytes() == b"keep"


def test_export_preview_surfaces_missing_powershell(tmp_path: Path) -> None:
    source = tmp_path / "drawing.vsdx"
    source.write_bytes(b"vsdx")

    def unavailable_runner(args, **kwargs):
        raise FileNotFoundError(args[0])

    with pytest.raises(PreviewError, match="could not run"):
        export_vsdx_preview(
            source,
            tmp_path / "preview.png",
            runner=unavailable_runner,
            platform_name="nt",
        )


def test_export_preview_does_not_follow_destination_symlink_created_during_export(
    tmp_path: Path,
) -> None:
    source = tmp_path / "drawing.vsdx"
    source.write_bytes(b"vsdx")
    destination = tmp_path / "preview.png"
    victim = tmp_path / "victim.png"
    victim.write_bytes(b"keep")
    runner = FakeRunner()

    def racing_runner(args, **kwargs):
        destination.symlink_to(victim)
        return runner(args, **kwargs)

    result = export_vsdx_preview(
        source,
        destination,
        runner=racing_runner,
        platform_name="nt",
    )

    assert result == destination
    assert not destination.is_symlink()
    assert destination.read_bytes() == b"visio-png"
    assert victim.read_bytes() == b"keep"
