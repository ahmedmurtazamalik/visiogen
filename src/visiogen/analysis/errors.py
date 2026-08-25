"""Typed failures raised by the document-analysis workstream."""


class AnalysisError(Exception):
    """Base class for controlled analysis failures."""


class CandidateClassificationError(AnalysisError):
    """A classifier returned incomplete or invalid candidate decisions."""


class ImagePreparationError(AnalysisError):
    """A selected candidate could not be decoded or prepared safely."""
