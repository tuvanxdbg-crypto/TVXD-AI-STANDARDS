"""Structured error taxonomy (docs/M02_STANDARDS_GATEWAY.md, section "Errors")."""
from __future__ import annotations

ERROR_CODES = {
    "INVALID_REQUEST": "The request does not match the input schema or lacks required data.",
    "INDEX_INVALID": "INDEX.yaml is missing, unreadable or fails validation; the Gateway fails closed.",
    "SOURCE_NOT_ALLOWED": "The document, path or NotebookLM source is outside the configured whitelist/root.",
    "SOURCE_NOT_FOUND": "The document, version, file or clause does not exist.",
    "VERSION_AMBIGUOUS": "More than one version could apply; the Gateway will not choose.",
    "SOURCE_DRIFT": "The source content or sync identity no longer matches the hash recorded in INDEX.",
    "APPLICABILITY_UNKNOWN": "Applicability cannot be determined from INDEX and the request context.",
    "BACKEND_UNAVAILABLE": "A retrieval backend is disabled, failed or is unreachable.",
    "AUTH_REQUIRED": "The backend needs the owner to sign in; the Gateway never signs in by itself.",
    "TIMEOUT": "A backend call or the bounded retry budget timed out.",
    "UNSUPPORTED_FORMAT": "The source format is not supported for extraction in this version.",
    "EXTRACTION_FAILED": "The source could not be decoded or exceeds extraction limits.",
    "INTERNAL_ERROR": "Unexpected Gateway failure (details are not exposed).",
}


class GatewayError(Exception):
    """An error returned to the caller as structured data, never as free text."""

    def __init__(self, code: str, message: str, *, retryable: bool = False, details: dict | None = None):
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "retryable": self.retryable,
                "details": self.details}
