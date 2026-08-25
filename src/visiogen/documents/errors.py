"""Typed failures for untrusted PDF and DOCX admission and extraction."""


class DocumentError(RuntimeError):
    """Base class for deterministic document-processing failures."""


class UnsupportedDocumentError(DocumentError):
    """Raised when the input is not a supported PDF or DOCX package."""


class DocumentTypeMismatchError(UnsupportedDocumentError):
    """Raised when the extension and inspected content disagree."""


class EncryptedDocumentError(DocumentError):
    """Raised when document content requires decryption."""


class UnsafeDocumentError(DocumentError):
    """Raised when a document contains an unsafe package construct."""


class DocumentLimitExceededError(UnsafeDocumentError):
    """Raised when a configured resource limit would be exceeded."""


class DocumentExtractionError(DocumentError):
    """Raised when an admitted document cannot be decomposed deterministically."""


class DocumentRenderError(DocumentExtractionError):
    """Raised when a bounded external document renderer fails."""
