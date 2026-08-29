"""
Per spec section 36: never show raw technical errors to users. Every
domain error raises one of these, and main.py's exception handler turns
them into a consistent, branded JSON shape the frontend can render as a
polished state instead of a stack trace.
"""


class PairzaError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str, code: str | None = None):
        self.message = message
        if code:
            self.code = code
        super().__init__(message)


class NotFoundError(PairzaError):
    status_code = 404
    code = "not_found"


class UnauthorizedError(PairzaError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(PairzaError):
    status_code = 403
    code = "forbidden"


class ConflictError(PairzaError):
    status_code = 409
    code = "conflict"


class RateLimitedError(PairzaError):
    status_code = 429
    code = "rate_limited"


class ValidationFailedError(PairzaError):
    status_code = 422
    code = "validation_failed"
