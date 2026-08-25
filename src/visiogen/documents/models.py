"""Strict provider-independent contracts for normalized document evidence."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DocumentKind = Literal["pdf", "docx"]
CoverageStatus = Literal["complete", "partial", "not_available"]
WarningSeverity = Literal["info", "warning", "error"]
TextOrigin = Literal[
    "native",
    "caption",
    "alt_text",
    "header",
    "footer",
    "footnote",
    "endnote",
    "ocr",
]
AssetOrigin = Literal["embedded", "page_render", "document_drawing"]


class DocumentModel(BaseModel):
    """Strict base for mechanically produced document records."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class NormalizedBox(DocumentModel):
    """Top-left-origin region in normalized 0..1 source coordinates."""

    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_area(self) -> NormalizedBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("Normalized box must have positive width and height")
        return self


class SourceLocation(DocumentModel):
    """Stable location of text or visual evidence within the source document."""

    page_number: int | None = Field(default=None, ge=1)
    part_name: str | None = None
    block_id: str | None = None
    paragraph_index: int | None = Field(default=None, ge=0)
    relationship_id: str | None = None
    asset_id: str | None = None
    bbox: NormalizedBox | None = None


class TextBlock(DocumentModel):
    """One ordered text block recovered mechanically or by explicit OCR."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    origin: TextOrigin
    style_name: str | None = None
    order: int = Field(ge=0)
    location: SourceLocation


class VisualAsset(DocumentModel):
    """One embedded or rendered visual asset bound to source coordinates."""

    id: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    origin: AssetOrigin
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int = Field(ge=0)
    artifact_path: str = Field(min_length=1)
    width_px: int | None = Field(default=None, gt=0)
    height_px: int | None = Field(default=None, gt=0)
    location: SourceLocation

    @model_validator(mode="after")
    def validate_dimensions(self) -> VisualAsset:
        if (self.width_px is None) != (self.height_px is None):
            raise ValueError("Visual asset width and height must be supplied together")
        path = PurePosixPath(self.artifact_path)
        if "\\" in self.artifact_path or path.is_absolute() or ".." in path.parts:
            raise ValueError("Visual asset artifact path must remain inside the bundle")
        return self


class ExtractionWarning(DocumentModel):
    """One explicit limitation or recoverable problem found during extraction."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: WarningSeverity = "warning"
    location: SourceLocation | None = None


class CoverageReport(DocumentModel):
    """Honest record of which document modalities were inspected."""

    native_text: CoverageStatus
    embedded_media: CoverageStatus
    rendered_pages: CoverageStatus
    word_drawings: CoverageStatus = "not_available"


class DocumentSnapshot(DocumentModel):
    """Normalized deterministic output shared by later analysis stages."""

    source_id: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_name: str = Field(min_length=1)
    document_kind: DocumentKind
    media_type: str = Field(min_length=1)
    byte_size: int = Field(gt=0)
    page_count: int | None = Field(default=None, ge=1)
    text_blocks: list[TextBlock] = Field(default_factory=list)
    visual_assets: list[VisualAsset] = Field(default_factory=list)
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    coverage: CoverageReport

    @model_validator(mode="after")
    def validate_references(self) -> DocumentSnapshot:
        text_ids = [block.id for block in self.text_blocks]
        asset_ids = [asset.id for asset in self.visual_assets]
        if len(text_ids) != len(set(text_ids)):
            raise ValueError("Text block IDs must be unique")
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("Visual asset IDs must be unique")
        known_assets = set(asset_ids)
        locations = [block.location for block in self.text_blocks]
        locations.extend(asset.location for asset in self.visual_assets)
        locations.extend(
            warning.location for warning in self.warnings if warning.location is not None
        )
        for location in locations:
            if location.asset_id is not None and location.asset_id not in known_assets:
                raise ValueError(f"Location references unknown asset '{location.asset_id}'")
            if (
                self.page_count is not None
                and location.page_number is not None
                and location.page_number > self.page_count
            ):
                raise ValueError("Location page exceeds document page count")
        return self
