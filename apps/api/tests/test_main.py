import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.ocr.engine import registry
from app.worker import WorkerSettings, build_redis_settings, ping


def test_health는_200과_상태를_돌려준다() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_앱_시작_시_OCR_엔진이_레지스트리에_등록된다() -> None:
    assert "paddleocr" in registry.names()


async def test_ping_작업은_pong을_돌려주고_워커에_등록돼_있다() -> None:
    assert await ping({}) == "pong"
    assert ping in WorkerSettings.functions


def test_워커는_REDIS_URL_환경변수를_연결_설정에_쓴다(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/2")

    settings = build_redis_settings()

    assert (settings.host, settings.port, settings.database) == ("redis", 6379, 2)
