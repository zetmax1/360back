"""
Centralised error handling.

All application errors are raised as AppError (or its subclasses) and
converted to the standard JSON envelope by the global exception handler
registered in main.py:

  {
    "error": {
      "code": "SCENE_NOT_FOUND",
      "message": "Scene with id '...' does not exist",
      "field": null
    }
  }
"""
from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse


# ── Base application error ────────────────────────────────────────────────────

class AppError(Exception):
    """Base class for all domain-level errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        field: str | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message
        self.field = field
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        super().__init__(message)


# ── 400 Bad Request ──────────────────────────────────────────────────────────

class ValidationError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "VALIDATION_ERROR"


class InvalidDegreeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_DEGREE"


class SelfLinkError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "SELF_LINK"


class CrossTourLinkError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "CROSS_TOUR_LINK"


class DuplicateLinkError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "DUPLICATE_LINK"


class UploadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "UPLOAD_TOO_LARGE"


class InvalidImageTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "INVALID_IMAGE_TYPE"


class InvalidAspectRatioError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_ASPECT_RATIO"


# ── 401 / 403 ────────────────────────────────────────────────────────────────

class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"


class TourNotPublishedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "TOUR_NOT_PUBLISHED"


# ── 404 Not Found ────────────────────────────────────────────────────────────

class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"


# ── 409 Conflict ─────────────────────────────────────────────────────────────

class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"


# ── Global exception handlers ────────────────────────────────────────────────

def _error_response(error: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "field": error.field,
            }
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _error_response(exc)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle Pydantic / FastAPI request-validation errors."""
    from fastapi.exceptions import RequestValidationError

    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    field = errors[0]["loc"][-1] if errors else None
    message = errors[0]["msg"] if errors else "Request validation failed"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "field": field,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all so we never leak Python tracebacks."""
    import logging
    logging.getLogger(__name__).exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred.",
                "field": None,
            }
        },
    )
