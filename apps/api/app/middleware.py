"""순수 ASGI 미들웨어: requestId 부여와 접근 로그, 간단한 레이트 리밋."""
import time
import uuid
from typing import Any

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.exceptions import RateLimitedError, error_body

REQUEST_ID_HEADER = "X-Request-ID"
logger = structlog.get_logger("doculens.http")


def _parse_request_id(value: str | None) -> str:
    """클라이언트가 보낸 값은 UUID일 때만 받는다 (로그 주입 방지). 아니면 새로 만든다."""
    if value:
        try:
            return str(uuid.UUID(value))
        except ValueError:
            pass
    return str(uuid.uuid4())


def get_request_id(scope: Scope) -> str | None:
    state: dict[str, Any] = scope.get("state") or {}
    return state.get("request_id")


class RequestIdMiddleware:
    """requestId를 request.state, 응답 헤더, 로그 컨텍스트에 심고 요청당 한 줄 로그를 남긴다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _parse_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        scope.setdefault("state", {})["request_id"] = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(requestId=request_id)

        status = 500
        started = time.perf_counter()

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # 쿼리스트링과 본문은 개인정보가 들어갈 수 있어 기록하지 않는다
            logger.info(
                "request_completed",
                requestId=request_id,
                method=scope["method"],
                path=scope["path"],
                status=status,
                durationMs=round((time.perf_counter() - started) * 1000, 1),
            )
            structlog.contextvars.clear_contextvars()


class RateLimitMiddleware:
    """IP당 고정 윈도우(60초) 레이트 리밋. 프로세스 메모리에만 두므로 인스턴스마다 따로 센다."""

    WINDOW_SECONDS = 60
    MAX_TRACKED_CLIENTS = 10_000

    def __init__(
        self, app: ASGIApp, limit_per_minute: int, exempt_paths: frozenset[str] = frozenset()
    ) -> None:
        self.app = app
        self.limit = limit_per_minute
        self.exempt_paths = exempt_paths
        self._windows: dict[str, tuple[float, int]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.limit <= 0 or scope["path"] in self.exempt_paths:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        key = client[0] if client else "unknown"
        retry_after = self._hit(key)
        if retry_after is None:
            await self.app(scope, receive, send)
            return

        error = RateLimitedError("요청이 너무 많습니다. 잠시 후 다시 시도해 주세요")
        logger.warning("rate_limited", requestId=get_request_id(scope), path=scope["path"])
        response = JSONResponse(
            error_body(error.code, error.message, get_request_id(scope)),
            status_code=error.status_code,
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)

    def _hit(self, key: str) -> int | None:
        """허용되면 None, 막히면 재시도까지 남은 초를 돌려준다."""
        now = time.monotonic()
        if len(self._windows) > self.MAX_TRACKED_CLIENTS:
            self._windows = {
                k: v for k, v in self._windows.items() if now - v[0] < self.WINDOW_SECONDS
            }
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self.WINDOW_SECONDS:
            start, count = now, 0
        if count >= self.limit:
            return max(1, int(self.WINDOW_SECONDS - (now - start)) + 1)
        self._windows[key] = (start, count + 1)
        return None
