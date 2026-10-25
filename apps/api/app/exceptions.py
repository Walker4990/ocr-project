"""도메인 예외. 핸들러(app/error_handlers.py)가 일관된 응답 형식으로 변환한다."""
from typing import Any


class DomainError(Exception):
    """모든 도메인 예외의 부모. 하위 클래스가 HTTP 상태와 에러 코드를 정한다."""

    status_code = 400
    code = "DOMAIN_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    status_code = 422
    code = "VALIDATION_ERROR"


class NotFoundError(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(DomainError):
    status_code = 409
    code = "CONFLICT"


class RateLimitedError(DomainError):
    status_code = 429
    code = "RATE_LIMITED"


def error_body(
    code: str, message: str, request_id: str | None, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """모든 에러 응답이 공유하는 본문 형식."""
    error: dict[str, Any] = {"code": code, "message": message, "requestId": request_id}
    if details:
        error["details"] = details
    return {"error": error}
