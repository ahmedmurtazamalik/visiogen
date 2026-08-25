"""Safe PDF and DOCX decomposition owned by the analysis workstream.

This package remains independent of AI providers so document extraction can be
tested deterministically and reused by future analysis providers.
"""

from visiogen.documents.models import DocumentSnapshot
from visiogen.documents.extractor import extract_document
from visiogen.documents.sniffing import AdmittedDocument, admit_document

__all__ = ["AdmittedDocument", "DocumentSnapshot", "admit_document", "extract_document"]
