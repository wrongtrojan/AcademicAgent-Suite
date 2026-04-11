from enum import Enum


class ErrorCode(str, Enum):
    INVALID_ENVELOPE = "INVALID_ENVELOPE"
    UNKNOWN_SERVICE = "UNKNOWN_SERVICE"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    DB_ERROR = "DB_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL = "INTERNAL"


class ProtocolError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
