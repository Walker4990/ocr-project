"""예외를 일관된 JSON 응답으로 변환한다. 모든 예외는 requestId와 함께 로깅한다."""
from http import HTTPStatus

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions import DomainError, error_body
from app.middleware import REQUEST_ID_HEADER, get_request_id

logger = structlog.get_logger("doculens.errors")

_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def _response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[dict[str, str]] | None = None,
) -> JSONResponse:
    request_id = get_request_id(request.scope)
    # 500은 미들웨어 바깥(ServerErrorMiddleware)에서 만들어지므로 헤더를 직접 붙인다
    headers = {REQUEST_ID_HEADER: request_id} if request_id else None
    return JSONResponse(
        error_body(code, message, request_id, details), status_code=status, headers=headers
    )


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    logger.warning(
        "domain_error",
        requestId=get_request_id(request.scope),
        code=exc.code,
        path=request.url.path,
    )
    return _response(request, exc.status_code, exc.code, exc.message)


async def handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
    logger.warning(
        "http_error",
        requestId=get_request_id(request.scope),
        status=exc.status_code,
        path=request.url.path,
    )
    return _response(request, exc.status_code, code, HTTPStatus(exc.status_code).phrase)


async def handle_request_validation(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    # 입력 값 자체는 개인정보일 수 있어 응답과 로그에 담지 않고 위치와 사유만 낸다
    details = [
        {"loc": ".".join(str(part) for part in err["loc"]), "msg": err["msg"], "type": err["type"]}
        for err in exc.errors()
    ]
    logger.warning(
        "request_validation_failed",
        requestId=get_request_id(request.scope),
        path=request.url.path,
        fields=[d["loc"] for d in details],
    )
    return _response(request, 422, "VALIDATION_ERROR", "요청 값이 올바르지 않습니다", details)


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_error",
        requestId=get_request_id(request.scope),
        path=request.url.path,
        errorType=type(exc).__name__,
    )
    return _response(request, 500, "INTERNAL_ERROR", "서버 내부 오류가 발생했습니다")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_request_validation)
    app.add_exception_handler(Exception, handle_unexpected)
