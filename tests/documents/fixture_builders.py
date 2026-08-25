"""Deterministic, locally generated PDF and DOCX fixtures for A1 tests."""

from __future__ import annotations

import base64
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def write_text_pdf(
    path: Path,
    text: str = "Sensor to Processor",
    *,
    javascript: bool = False,
    action: str | None = None,
    attachment: bool = False,
    encrypted: bool = False,
) -> Path:
    """Write one valid Helvetica text page without third-party fixture tooling."""

    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 18 Tf 72 720 Td ({escaped}) Tj ET\n".encode("ascii")
    objects = [
        b"",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"endstream",
    ]
    catalog = b"<< /Type /Catalog /Pages 2 0 R"
    next_number = 6
    if javascript or action:
        catalog += f" /OpenAction {next_number} 0 R".encode()
        if javascript:
            objects.append(b"<< /S /JavaScript /JS (app.alert('unsafe')) >>")
        elif action == "launch":
            objects.append(b"<< /S /Launch /F (unsafe.bin) >>")
        elif action == "external_uri":
            objects.append(b"<< /S /URI /URI (https://example.invalid/) >>")
        else:
            raise ValueError(f"Unknown PDF fixture action: {action}")
        next_number += 1
    if attachment:
        specification_number = next_number
        stream_number = next_number + 1
        catalog += (
            b" /Names << /EmbeddedFiles << /Names [(payload.txt) "
            + f"{specification_number} 0 R".encode()
            + b"] >> >>"
        )
        objects.append(
            b"<< /Type /Filespec /F (payload.txt) /EF << /F "
            + f"{stream_number} 0 R".encode()
            + b" >> >>"
        )
        payload = b"unsafe attachment"
        objects.append(
            b"<< /Type /EmbeddedFile /Length "
            + str(len(payload)).encode()
            + b" >>\nstream\n"
            + payload
            + b"\nendstream"
        )
        next_number += 2
    encrypt_number = None
    if encrypted:
        encrypt_number = next_number
        objects.append(b"<< /Filter /Standard /V 1 /R 2 /O () /U () /P -4 >>")
    objects[0] = catalog + b" >>"
    content = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(content))
        content.extend(f"{number} 0 obj\n".encode("ascii"))
        content.extend(value)
        content.extend(b"\nendobj\n")
    xref = len(content)
    content.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    content.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R"
    if encrypt_number is not None:
        trailer += f" /Encrypt {encrypt_number} 0 R"
    trailer += f" >>\nstartxref\n{xref}\n%%EOF\n"
    content.extend(trailer.encode("ascii"))
    path.write_bytes(content)
    return path


def write_diagram_docx(
    path: Path,
    *,
    external_relationship: bool = False,
    embedded_object: bool = False,
    unsafe_xml: bool = False,
) -> Path:
    """Write a portable DOCX with native text, caption, alt text, and one PNG."""

    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
 <w:body>
  <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>System overview</w:t></w:r></w:p>
  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Processor</w:t></w:r></w:p></w:tc>
   <w:tc><w:p><w:r><w:t>Controller</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
  <w:p><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">
   <wp:extent cx="914400" cy="914400"/><wp:docPr id="1" name="Diagram" descr="Sensor diagram"/>
   <wp:cNvGraphicFramePr/>
   <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
    <pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="diagram.png"/><pic:cNvPicPr/></pic:nvPicPr>
     <pic:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
     <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="914400" cy="914400"/></a:xfrm>
      <a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
    </pic:pic>
   </a:graphicData></a:graphic>
  </wp:inline></w:drawing></w:r></w:p>
  <w:p><w:pPr><w:pStyle w:val="Caption"/></w:pPr><w:r><w:t>Figure 1</w:t></w:r></w:p>
  <w:sectPr><w:headerReference w:type="default" r:id="rId2"/><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440"
   w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body>
</w:document>""".encode()
    if unsafe_xml:
        document_xml = b'<!DOCTYPE x [<!ENTITY boom "unsafe">]><x>&boom;</x>'
    relationship = (
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="https://example.com/image.png" '
        'TargetMode="External"/>'
        if external_relationship
        else '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/diagram.png"/>'
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{relationship}<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        '</Relationships>'
    ).encode()
    content_types = b"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="xml" ContentType="application/xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
 <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
</Types>"""
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr(
            "_rels/.rels",
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rIdOffice" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            b'</Relationships>',
        )
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", rels_xml)
        archive.writestr(
            "word/header1.xml",
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b'<w:p><w:r><w:t>Confidential</w:t></w:r></w:p></w:hdr>',
        )
        archive.writestr("word/media/diagram.png", PNG_1X1)
        if embedded_object:
            archive.writestr("word/embeddings/object.bin", b"object")
    return path
