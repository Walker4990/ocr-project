"""OcrEngine Protocol, 데이터 구조, 엔진 선택 메커니즘 테스트."""
import numpy as np
import pytest
from numpy.typing import NDArray

from app.ocr.engine import (
    DEFAULT_ENGINE_NAME,
    ENGINE_ENV_VAR,
    EngineRegistry,
    OcrEngine,
    OcrPage,
    OcrToken,
    UnknownOcrEngineError,
)


class DummyEngine:
    """이미지 전체를 한 토큰으로 돌려주는 검증용 엔진."""

    name = "dummy"
    supports_gpu = False

    def recognize(self, image: NDArray[np.uint8]) -> OcrPage:
        height, width = image.shape[:2]
        token = OcrToken(text="더미", bbox=(0.0, 0.0, float(width), float(height)), confidence=1.0)
        return OcrPage(width=width, height=height, tokens=(token,))


class NotAnEngine:
    name = "broken"


def test_token_keeps_text_bbox_and_confidence() -> None:
    token = OcrToken(text="합계", bbox=(10.0, 20.0, 110.0, 60.0), confidence=0.93)
    assert token.text == "합계"
    assert token.bbox == (10.0, 20.0, 110.0, 60.0)
    assert token.confidence == 0.93


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_token_rejects_confidence_outside_unit_range(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        OcrToken(text="a", bbox=(0.0, 0.0, 1.0, 1.0), confidence=confidence)


@pytest.mark.parametrize("bbox", [(5.0, 0.0, 1.0, 1.0), (0.0, 5.0, 1.0, 1.0)])
def test_token_rejects_inverted_bbox(bbox: tuple[float, float, float, float]) -> None:
    with pytest.raises(ValueError, match="bbox"):
        OcrToken(text="a", bbox=bbox, confidence=0.5)


def test_token_is_immutable() -> None:
    token = OcrToken(text="a", bbox=(0.0, 0.0, 1.0, 1.0), confidence=0.5)
    with pytest.raises(AttributeError):
        token.text = "b"  # type: ignore[misc]  # pyright: ignore[reportAttributeAccessIssue]


def test_page_text_joins_tokens_in_order() -> None:
    tokens = tuple(
        OcrToken(text=text, bbox=(0.0, 0.0, 1.0, 1.0), confidence=0.9) for text in ("품목", "수량")
    )
    page = OcrPage(width=100, height=200, tokens=tokens)
    assert page.text == "품목\n수량"


def test_dummy_engine_satisfies_protocol() -> None:
    assert isinstance(DummyEngine(), OcrEngine)
    assert not isinstance(NotAnEngine(), OcrEngine)


def test_dummy_engine_recognize_returns_page_with_image_size() -> None:
    image = np.zeros((40, 30, 3), dtype=np.uint8)
    page = DummyEngine().recognize(image)
    assert (page.width, page.height) == (30, 40)
    assert page.tokens[0].text == "더미"


def test_registry_creates_registered_engine_by_name() -> None:
    registry = EngineRegistry()
    registry.register("dummy", DummyEngine)
    engine = registry.create("dummy")
    assert isinstance(engine, DummyEngine)


def test_registry_creates_new_instance_each_time() -> None:
    registry = EngineRegistry()
    registry.register("dummy", DummyEngine)
    assert registry.create("dummy") is not registry.create("dummy")


def test_registry_picks_engine_from_environment_variable() -> None:
    registry = EngineRegistry()
    registry.register("dummy", DummyEngine)
    engine = registry.create(environ={ENGINE_ENV_VAR: "dummy"})
    assert engine.name == "dummy"


def test_registry_explicit_name_beats_environment_variable() -> None:
    registry = EngineRegistry()
    registry.register("dummy", DummyEngine)
    registry.register("other", DummyEngine)
    engine = registry.create("dummy", environ={ENGINE_ENV_VAR: "other"})
    assert isinstance(engine, DummyEngine)


def test_registry_falls_back_to_default_engine_name() -> None:
    registry = EngineRegistry()
    registry.register(DEFAULT_ENGINE_NAME, DummyEngine)
    assert isinstance(registry.create(environ={}), DummyEngine)


def test_unknown_engine_error_names_the_engine_and_the_choices() -> None:
    registry = EngineRegistry()
    registry.register("dummy", DummyEngine)
    with pytest.raises(UnknownOcrEngineError, match="nope") as error:
        registry.create("nope")
    assert "dummy" in str(error.value)


def test_registering_same_name_twice_raises() -> None:
    registry = EngineRegistry()
    registry.register("dummy", DummyEngine)
    with pytest.raises(ValueError, match="dummy"):
        registry.register("dummy", DummyEngine)


def test_registry_lists_names_sorted() -> None:
    registry = EngineRegistry()
    registry.register("b", DummyEngine)
    registry.register("a", DummyEngine)
    assert registry.names() == ["a", "b"]
