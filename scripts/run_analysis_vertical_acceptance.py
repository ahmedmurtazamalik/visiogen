#!/usr/bin/env python3
"""Run fresh PDF and DOCX fixtures through the production A7 analysis pipeline."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import zlib

from PIL import Image, ImageDraw, ImageFont

from visiogen.analysis.production import build_codex_analysis_pipeline
from visiogen.config import Settings
from visiogen.documents.artifacts import publish_artifact_directory

_REPOSITORY = Path(__file__).resolve().parents[1]
_IMPLEMENTATION_FILES = (
    _REPOSITORY / "src/visiogen/analysis/pipeline.py",
    _REPOSITORY / "src/visiogen/analysis/artifacts.py",
    _REPOSITORY / "src/visiogen/analysis/production.py",
    _REPOSITORY / "src/visiogen/analysis/command.py",
    _REPOSITORY / "src/visiogen/cli.py",
    Path(__file__).resolve(),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _implementation_sha256() -> str:
    digest = hashlib.sha256()
    for path in _IMPLEMENTATION_FILES:
        digest.update(path.relative_to(_REPOSITORY).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def _diagram_png() -> bytes:
    image = Image.new("RGB", (1200, 620), "white")
    draw = ImageDraw.Draw(image)
    boxes = (
        ((60, 220, 310, 390), "Sensor"),
        ((475, 220, 725, 390), "Processor"),
        ((890, 220, 1140, 390), "Actuator"),
    )
    for box, label in boxes:
        draw.rounded_rectangle(box, radius=20, fill="#edf5ff", outline="#172554", width=6)
        bounds = draw.textbbox((0, 0), label, font=_font(38))
        draw.text(
            (
                (box[0] + box[2] - (bounds[2] - bounds[0])) // 2,
                (box[1] + box[3] - (bounds[3] - bounds[1])) // 2,
            ),
            label,
            fill="#111827",
            font=_font(38),
        )
    for start, end, label in (
        ((310, 305), (475, 305), "measurements"),
        ((725, 305), (890, 305), "commands"),
    ):
        draw.line((start, end), fill="#172554", width=7)
        draw.polygon(
            ((end[0], end[1]), (end[0] - 24, end[1] - 15), (end[0] - 24, end[1] + 15)),
            fill="#172554",
        )
        bounds = draw.textbbox((0, 0), label, font=_font(25))
        draw.text(
            ((start[0] + end[0] - (bounds[2] - bounds[0])) // 2, 255),
            label,
            fill="#111827",
            font=_font(25),
        )
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=9)
    return stream.getvalue()


def _pdf_object(content: bytearray, number: int, value: bytes, offsets: list[int]) -> None:
    offsets.append(len(content))
    content.extend(f"{number} 0 obj\n".encode())
    content.extend(value)
    content.extend(b"\nendobj\n")


def write_acceptance_pdf(path: Path, diagram_png: bytes) -> Path:
    """Create a single-page PDF with native prose and a raster diagram."""

    with Image.open(io.BytesIO(diagram_png)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        pixels = zlib.compress(rgb.tobytes(), level=9)
    page_stream = (
        b"BT /F1 20 Tf 54 742 Td (Control system overview) Tj ET\n"
        b"BT /F1 11 Tf 54 710 Td (The Sensor sends measurements to the Processor.) Tj ET\n"
        b"BT /F1 11 Tf 54 692 Td (The Processor sends commands to the Actuator.) Tj ET\n"
        b"q 504 0 0 260.4 54 350 cm /Im0 Do Q\n"
        b"BT /F1 10 Tf 54 325 Td (Figure 1. Control signal path.) Tj ET\n"
    )
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> /XObject << /Im0 5 0 R >> >> "
            b"/Contents 6 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} ".encode()
            + b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length "
            + str(len(pixels)).encode()
            + b" >>\nstream\n"
            + pixels
            + b"\nendstream"
        ),
        b"<< /Length "
        + str(len(page_stream)).encode()
        + b" >>\nstream\n"
        + page_stream
        + b"endstream",
    )
    content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        _pdf_object(content, number, value, offsets)
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode())
    content.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    path.write_bytes(content)
    return path


def write_acceptance_docx(path: Path, diagram_png: bytes) -> Path:
    """Create a portable DOCX with native prose and the same embedded diagram."""

    document = b"""<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
 <w:body>
  <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Control system overview</w:t></w:r></w:p>
  <w:p><w:r><w:t>The Sensor sends measurements to the Processor.</w:t></w:r></w:p>
  <w:p><w:r><w:t>The Processor sends commands to the Actuator.</w:t></w:r></w:p>
  <w:p><w:r><w:drawing><wp:inline><wp:extent cx="5486400" cy="2834640"/>
   <wp:docPr id="1" name="Control signal path" descr="Sensor to Processor to Actuator diagram"/>
   <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
    <pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="control-system.png"/><pic:cNvPicPr/></pic:nvPicPr>
     <pic:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
     <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="5486400" cy="2834640"/></a:xfrm>
      <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
    </pic:pic></a:graphicData></a:graphic>
  </wp:inline></w:drawing></w:r></w:p>
  <w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>Figure 1. Control signal path.</w:t></w:r></w:p>
  <w:sectPr><w:pgSz w:w="12240" w:h="15840"/></w:sectPr>
 </w:body>
</w:document>"""
    content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="xml" ContentType="application/xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    def write_member(archive: ZipFile, name: str, data: bytes) -> None:
        member = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        member.compress_type = ZIP_DEFLATED
        member.external_attr = 0o600 << 16
        archive.writestr(member, data)

    with ZipFile(path, "w") as archive:
        write_member(archive, "[Content_Types].xml", content_types)
        write_member(
            archive,
            "_rels/.rels",
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rIdOffice" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            b"</Relationships>",
        )
        write_member(archive, "word/document.xml", document)
        write_member(
            archive,
            "word/_rels/document.xml.rels",
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/control-system.png"/>'
            b"</Relationships>",
        )
        write_member(archive, "word/media/control-system.png", diagram_png)
    return path


def _verify_artifact_hashes(bundle: Path, manifest: dict[str, object]) -> list[str]:
    failures: list[str] = []
    for artifact in manifest["artifacts"]:
        path = bundle / artifact["path"]
        if not path.is_file():
            failures.append(f"missing artifact: {artifact['path']}")
        elif _sha256(path) != artifact["sha256"]:
            failures.append(f"artifact hash mismatch: {artifact['path']}")
        elif path.stat().st_size != artifact["byte_size"]:
            failures.append(f"artifact size mismatch: {artifact['path']}")
    return failures


def _bundle_sha256(bundle: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in bundle.rglob("*") if item.is_file()):
        digest.update(path.relative_to(bundle).as_posix().encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def _verify_case(case_id: str, source: Path, bundle: Path, report: Path) -> dict[str, object]:
    manifest = json.loads((bundle / "manifest.json").read_text())
    analysis = json.loads((bundle / "analysis.json").read_text())
    failures = _verify_artifact_hashes(bundle, manifest)
    if manifest["source_sha256"] != _sha256(source):
        failures.append("source hash mismatch")
    if manifest["source_byte_size"] != source.stat().st_size:
        failures.append("source size mismatch")
    if manifest["provider"] != "codex-cli" or not manifest["model"]:
        failures.append("provider/model provenance missing")
    if not manifest["schema_sha256"] or not manifest["tools"]:
        failures.append("schema/tool provenance missing")
    if manifest["total_model_calls"] < 4:
        failures.append("aggregate model-call provenance incomplete")
    for name in (
        "04-classification-trace.json",
        "05-classification-system-prompt.txt",
        "06-classification-user-prompt.txt",
        "08-classification-response.json",
        "analysis.json",
        "report.md",
    ):
        if not (bundle / name).is_file():
            failures.append(f"missing aggregate artifact: {name}")
    if analysis["status"] != "complete" or not analysis["candidates"]:
        failures.append("analysis did not complete at least one candidate")
    for candidate in analysis["candidates"]:
        candidate_id = candidate["candidate_id"]
        if candidate["status"] != "completed":
            failures.append(f"candidate did not complete: {candidate_id}")
            continue
        if candidate["model_calls"] < 3:
            failures.append(f"candidate model-call provenance incomplete: {candidate_id}")
        required = (
            "00-result.json",
            "14-validated-observations.json",
            "24-analyzed-diagram.json",
            "25-description.md",
            "30-selected-text-blocks.json",
            "34-document-claims.json",
            "40-alignments.json",
            "43-findings.json",
            "44-findings.md",
        )
        for name in required:
            if not (bundle / candidate_id / name).is_file():
                failures.append(f"missing candidate artifact: {candidate_id}/{name}")
        for trace_stage in ("observation", "reconstruction", "claims"):
            if not list((bundle / candidate_id / "traces").glob(f"{trace_stage}-*-response.json")):
                failures.append(f"missing {trace_stage} trace: {candidate_id}")
    if report.read_bytes() != (bundle / "report.md").read_bytes():
        failures.append("published report differs from private report")
    if list(bundle.rglob("*.vsdx")):
        failures.append("VSDX generation artifact appeared in analysis bundle")
    return {
        "id": case_id,
        "status": "passed" if not failures else "failed",
        "source": {
            "path": source.name,
            "sha256": _sha256(source),
            "byte_size": source.stat().st_size,
        },
        "bundle_sha256": _bundle_sha256(bundle),
        "candidate_count": len(analysis["candidates"]),
        "model_calls": manifest["total_model_calls"],
        "manifest": manifest,
        "failures": failures,
    }


def _codex_version(command: str) -> str:
    completed = subprocess.run(
        [command, "--version"], text=True, capture_output=True, check=True, timeout=15
    )
    return (completed.stdout or completed.stderr).strip().splitlines()[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Generate fresh fixtures without calling the provider",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    if output == _REPOSITORY or _REPOSITORY in output.parents:
        parser.error("Acceptance output must be outside the source checkout")

    settings = Settings(
        provider="codex",
        codex_model=args.model,
        timeout_seconds=args.timeout,
    )

    def build(stage: Path) -> dict[str, object]:
        inputs = stage / "inputs"
        inputs.mkdir()
        diagram = _diagram_png()
        (inputs / "control-system.png").write_bytes(diagram)
        sources = (
            ("fresh-pdf", write_acceptance_pdf(inputs / "fresh-control-system.pdf", diagram)),
            ("fresh-docx", write_acceptance_docx(inputs / "fresh-control-system.docx", diagram)),
        )
        if args.prepare_only:
            report = {
                "status": "prepared",
                "implementation_sha256": _implementation_sha256(),
                "cases": [
                    {
                        "id": case_id,
                        "source_sha256": _sha256(source),
                        "source_byte_size": source.stat().st_size,
                    }
                    for case_id, source in sources
                ],
            }
        else:
            cases = []
            for case_id, source in sources:
                case_root = stage / case_id
                pipeline = build_codex_analysis_pipeline(settings)
                result = pipeline.analyze(source, case_root / "bundle")
                report_path = case_root / "report.md"
                report_path.write_bytes((result.artifact_dir / "report.md").read_bytes())
                cases.append(
                    _verify_case(case_id, source, result.artifact_dir, report_path)
                )
            passed = all(case["status"] == "passed" for case in cases)
            report = {
                "status": "passed" if passed else "failed",
                "source_state": "content-addressed A7 implementation and fresh fixtures",
                "source_revision": subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=_REPOSITORY,
                    text=True,
                    capture_output=True,
                    check=True,
                ).stdout.strip(),
                "source_worktree_clean": not bool(
                    subprocess.run(
                        ["git", "status", "--porcelain"],
                        cwd=_REPOSITORY,
                        text=True,
                        capture_output=True,
                        check=True,
                    ).stdout.strip()
                ),
                "implementation_sha256": _implementation_sha256(),
                "provider": "codex-cli",
                "provider_version": _codex_version(settings.codex_command),
                "model": args.model,
                "case_count": len(cases),
                "cases": cases,
            }
        (stage / "acceptance-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        return report

    report = publish_artifact_directory(output, build)
    print(f"A7 vertical acceptance: {report['status']}")
    print(f"Evidence: {output}")
    return 0 if report["status"] in {"passed", "prepared"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
