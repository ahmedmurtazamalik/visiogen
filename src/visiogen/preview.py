"""Authoritative Microsoft Visio preview export for visual critique."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory


class PreviewError(RuntimeError):
    """Raised when Microsoft Visio cannot export a preview image."""


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]

_VISIO_EXPORT_SCRIPT = r'''param(
    [Parameter(Mandatory=$true)][string]$SourcePath,
    [Parameter(Mandatory=$true)][string]$DestinationPath
)
$ErrorActionPreference = "Stop"
$visio = $null
$document = $null
try {
    $visio = New-Object -ComObject Visio.Application
    $visio.Visible = $false
    $document = $visio.Documents.OpenEx($SourcePath, 2)
    if ($document.Pages.Count -lt 1) {
        throw "The Visio document has no pages"
    }
    $page = $document.Pages.Item(1)
    $page.Export($DestinationPath)
}
finally {
    if ($null -ne $document) {
        try { $document.Close() } catch {}
    }
    if ($null -ne $visio) {
        try { $visio.Quit() } catch {}
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
'''


def export_vsdx_preview(
    source: str | Path,
    destination: str | Path,
    *,
    runner: CommandRunner = subprocess.run,
    platform_name: str = os.name,
    powershell_command: str = "powershell.exe",
) -> Path:
    """Export page one to PNG through installed desktop Microsoft Visio.

    Microsoft Visio on Windows is the only supported preview authority. The
    function fails explicitly on other platforms instead of substituting a
    third-party VSDX renderer.
    """

    input_path = Path(source)
    output_path = Path(destination)
    if not input_path.is_file():
        raise PreviewError(f"VSDX source was not found: {input_path}")
    if platform_name != "nt":
        raise PreviewError("Microsoft Visio preview export requires Windows and desktop Visio")
    if output_path.suffix.lower() != ".png":
        raise PreviewError("Microsoft Visio preview destination must be a PNG file")
    if output_path.is_symlink() or output_path.exists():
        raise PreviewError("Microsoft Visio preview destination must not already exist")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="visiogen-visio-preview-") as directory:
        temporary = Path(directory)
        script_path = Path(directory) / "export-preview.ps1"
        script_path.write_text(_VISIO_EXPORT_SCRIPT, encoding="utf-8", newline="")
        exported_path = temporary / "visio-export.png"
        args = [
            powershell_command,
            "-NoProfile",
            "-NonInteractive",
            "-Sta",
            "-File",
            str(script_path),
            str(input_path.resolve()),
            str(exported_path.resolve()),
        ]
        try:
            completed = runner(
                args,
                text=True,
                capture_output=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as error:
            raise PreviewError("Microsoft Visio preview export could not run") from error
        if completed.returncode != 0:
            raise PreviewError(
                f"Microsoft Visio preview export failed with status {completed.returncode}"
            )

        if not exported_path.is_file():
            raise PreviewError("Microsoft Visio did not produce a PNG preview")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
        )
        staged = Path(temporary_name)
        try:
            destination_file = os.fdopen(descriptor, "wb")
            descriptor = -1
            with exported_path.open("rb") as source_file, destination_file:
                shutil.copyfileobj(source_file, destination_file)
            staged.chmod(0o600)
            staged.replace(output_path)
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            staged.unlink(missing_ok=True)
            raise
    return output_path
