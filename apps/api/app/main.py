"""FastAPI 진입점. 엔드포인트는 controllers/ 의 라우터로 추가한다."""
from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.controllers import health_controller
from app.error_handlers import register_error_handlers
from app.health import DatabaseChecker, HealthChecker, RedisChecker
from app.logging_config import configure_logging
from app.middleware import REQUEST_ID_HEADER, RateLimitMiddleware, RequestIdMiddleware
from app.ocr import engines as engines  # import하면 OCR 엔진이 레지스트리에 등록된다
from app.services.health_service import HealthService


def create_app(
    settings: Settings | None = None, health_checkers: Sequence[HealthChecker] | None = None
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, settings.log_json)
    if health_checkers is None:
        health_checkers = [DatabaseChecker(settings.database_url), RedisChecker(settings.redis_url)]

    app = FastAPI(title="DocuLens API")
    app.state.health_service = HealthService(health_checkers)
    register_error_handlers(app)
    app.include_router(health_controller.router)

    # 나중에 추가한 미들웨어가 바깥쪽이다: CORS > requestId > 레이트 리밋 > 라우터
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.rate_limit_per_minute,
        exempt_paths=frozenset({"/health"}),
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    return app


app = create_app()
