"""arq 워커 진입점. 작업 함수는 이후 태스크에서 `functions`에 추가한다."""
import os
from collections.abc import Awaitable, Callable
from typing import Any

from arq.connections import RedisSettings

from app.ocr import engines as engines  # import하면 OCR 엔진이 레지스트리에 등록된다

DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def build_redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.environ.get("REDIS_URL", DEFAULT_REDIS_URL))


async def ping(ctx: dict[str, Any]) -> str:
    """워커 연결 확인용 작업. arq는 등록된 함수가 하나도 없으면 시작하지 않는다."""
    return "pong"


class WorkerSettings:
    functions: list[Callable[..., Awaitable[Any]]] = [ping]
    redis_settings = build_redis_settings()
    # `arq --check`가 이 주기로 남기는 헬스 키를 확인한다 (docker 헬스체크용)
    health_check_interval = 10
