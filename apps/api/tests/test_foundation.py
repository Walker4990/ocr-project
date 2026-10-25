"""태스크 3: requestId, 도메인 예외 핸들러, 헬스 체크, CORS, 레이트 리밋 테스트."""
import uuid
from collections.abc import Iterator

import pytest
import structlog
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.health import CheckResult, DatabaseChecker, HealthChecker, RedisChecker
from app.main import create_app


class FakeChecker:
    def __init__(self, name: str, result: CheckResult) -> None:
        self.name = name
        self._result: CheckResult = result

    async def check(self) -> CheckResult:
        return self._result


def build_app(
    *,
    checkers: list[HealthChecker] | None = None,
    rate_limit: int = 1000,
    cors: str = "http://localhost:3000",
) -> FastAPI:
    app = create_app(
        Settings(cors_origins=cors, rate_limit_per_minute=rate_limit),
        health_checkers=checkers if checkers is not None else [],
    )
    router = APIRouter()

    @router.get("/_t/not-found")
    def not_found() -> None:
        raise NotFoundError("문서를 찾을 수 없습니다")

    @router.get("/_t/invalid")
    def invalid() -> None:
        raise ValidationError("파일 형식이 올바르지 않습니다")

    @router.get("/_t/conflict")
    def conflict() -> None:
        raise ConflictError("이미 처리 중입니다")

    @router.get("/_t/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    @router.get("/_t/int/{value}")
    def int_param(value: int) -> dict[str, int]:
        return {"value": value}

    app.include_router(router)
    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(build_app(), raise_server_exceptions=False) as c:
        yield c


def test_모든_응답에_UUID_requestId_헤더가_붙는다(client: TestClient) -> None:
    response = client.get("/health")

    uuid.UUID(response.headers["X-Request-ID"])


def test_클라이언트가_보낸_유효한_UUID_requestId는_그대로_쓴다(client: TestClient) -> None:
    rid = str(uuid.uuid4())

    response = client.get("/health", headers={"X-Request-ID": rid})

    assert response.headers["X-Request-ID"] == rid


def test_유효하지_않은_requestId는_버리고_새로_만든다(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "bad\nvalue"})

    uuid.UUID(response.headers["X-Request-ID"])


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/_t/not-found", 404, "NOT_FOUND"),
        ("/_t/invalid", 422, "VALIDATION_ERROR"),
        ("/_t/conflict", 409, "CONFLICT"),
    ],
)
def test_도메인_예외는_일관된_형식과_requestId로_변환된다(
    client: TestClient, path: str, status: int, code: str
) -> None:
    response = client.get(path)

    body = response.json()
    assert response.status_code == status
    assert body["error"]["code"] == code
    assert body["error"]["requestId"] == response.headers["X-Request-ID"]
    assert body["error"]["message"]


def test_요청_검증_실패도_같은_형식이다(client: TestClient) -> None:
    response = client.get("/_t/int/abc")

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["requestId"] == response.headers["X-Request-ID"]


def test_없는_경로도_같은_형식의_404다(client: TestClient) -> None:
    response = client.get("/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_예상치_못한_예외는_500이고_내부_내용을_노출하지_않는다(client: TestClient) -> None:
    response = client.get("/_t/boom")

    body = response.json()
    assert response.status_code == 500
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
    assert body["error"]["requestId"] == response.headers["X-Request-ID"]


def test_예외는_삼키지_않고_requestId와_함께_로깅된다() -> None:
    app = build_app()
    with structlog.testing.capture_logs() as logs:
        with TestClient(app, raise_server_exceptions=False) as c:
            response = c.get("/_t/boom")

    errors = [entry for entry in logs if entry["log_level"] == "error"]
    assert errors
    assert errors[0]["requestId"] == response.headers["X-Request-ID"]


def test_요청_로그에_requestId가_있고_쿼리와_본문은_없다() -> None:
    app = build_app()
    with structlog.testing.capture_logs() as logs:
        with TestClient(app) as c:
            response = c.get("/health?name=홍길동")

    entries = [e for e in logs if e["event"] == "request_completed"]
    assert len(entries) == 1
    assert entries[0]["requestId"] == response.headers["X-Request-ID"]
    assert entries[0]["path"] == "/health"
    assert entries[0]["status"] == 200
    assert "홍길동" not in str(entries[0])


def test_도메인_예외_로그는_경고_수준이다() -> None:
    app = build_app()
    with structlog.testing.capture_logs() as logs:
        with TestClient(app) as c:
            c.get("/_t/not-found")

    assert any(e["event"] == "domain_error" and e["log_level"] == "warning" for e in logs)


def test_health는_체커가_없으면_ok다(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {}}


def test_health는_체커_결과를_모두_보여준다() -> None:
    checkers: list[HealthChecker] = [
        FakeChecker("database", "skipped"),
        FakeChecker("redis", "ok"),
    ]
    with TestClient(build_app(checkers=checkers)) as c:
        response = c.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "skipped", "redis": "ok"},
    }


def test_health는_하나라도_down이면_503이다() -> None:
    checkers: list[HealthChecker] = [
        FakeChecker("database", "ok"),
        FakeChecker("redis", "down"),
    ]
    with TestClient(build_app(checkers=checkers)) as c:
        response = c.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "checks": {"database": "ok", "redis": "down"}}


def test_체커가_예외를_던지면_down으로_처리하고_로깅한다() -> None:
    class Exploding:
        name = "redis"

        async def check(self) -> CheckResult:
            raise ConnectionError("refused")

    app = build_app(checkers=[Exploding()])  # create_app이 로깅을 설정하므로 캡처 전에 만든다
    with structlog.testing.capture_logs() as logs:
        with TestClient(app) as c:
            response = c.get("/health")

    assert response.status_code == 503
    assert response.json()["checks"] == {"redis": "down"}
    assert any(e["event"] == "health_check_failed" for e in logs)


def test_CORS는_허용된_출처에만_헤더를_준다() -> None:
    with TestClient(build_app(cors="http://localhost:3000")) as c:
        allowed = c.get("/health", headers={"Origin": "http://localhost:3000"})
        denied = c.get("/health", headers={"Origin": "http://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers
    assert "X-Request-ID" in allowed.headers["access-control-expose-headers"]


def test_레이트_리밋을_넘으면_429와_requestId를_돌려준다() -> None:
    with TestClient(build_app(rate_limit=3)) as c:
        statuses = [c.get("/_t/not-found").status_code for _ in range(3)]
        limited = c.get("/_t/not-found")

    assert statuses == [404, 404, 404]
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert limited.json()["error"]["requestId"] == limited.headers["X-Request-ID"]
    assert int(limited.headers["Retry-After"]) >= 1


def test_health는_레이트_리밋_대상이_아니다() -> None:
    with TestClient(build_app(rate_limit=1)) as c:
        statuses = {c.get("/health").status_code for _ in range(5)}

    assert statuses == {200}


def test_설정은_환경변수에서_읽고_쉼표로_출처를_나눈다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "7")

    settings = Settings()

    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
    assert settings.rate_limit_per_minute == 7


async def test_설정이_없으면_DB와_Redis_체크는_skipped다() -> None:
    assert await DatabaseChecker(None).check() == "skipped"
    assert await RedisChecker(None).check() == "skipped"


async def test_DB_체커는_SELECT_1로_ok를_확인한다() -> None:
    assert await DatabaseChecker("sqlite://").check() == "ok"


async def test_Redis에_연결할_수_없으면_down이다() -> None:
    checker = RedisChecker("redis://127.0.0.1:1/0", timeout_seconds=0.5)

    assert await checker.check() == "down"
