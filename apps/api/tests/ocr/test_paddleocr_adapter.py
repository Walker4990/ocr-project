"""PaddleOCR 어댑터 테스트. 변환 로직은 가짜 predictor로, 실제 모델은 slow 마커로 검증한다."""
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from app.ocr.engine import EngineRegistry, OcrEngine, registry
from app.ocr.engines.paddleocr_adapter import (
    PaddleOcrEngine,
    build_paddleocr,
    resolve_use_gpu,
)

GOLDEN_DIR = Path(__file__).resolve().parents[4] / "samples" / "golden"


class FakePredictor:
    def __init__(self, results: list[Mapping[str, Any]]) -> None:
        self._results = results
        self.received: list[NDArray[np.uint8]] = []

    def predict(self, image: NDArray[np.uint8]) -> list[Mapping[str, Any]]:
        self.received.append(image)
        return self._results


def blank_image(width: int = 200, height: int = 100) -> NDArray[np.uint8]:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def make_engine(results: list[Mapping[str, Any]]) -> tuple[PaddleOcrEngine, FakePredictor]:
    predictor = FakePredictor(results)
    return PaddleOcrEngine(predictor=predictor, use_gpu=False), predictor


def test_엔진_프로토콜을_만족한다() -> None:
    engine, _ = make_engine([])
    assert isinstance(engine, OcrEngine)
    assert engine.name == "paddleocr"
    assert engine.supports_gpu is False


def test_다각형을_바깥_사각형으로_바꾼다() -> None:
    polys = [np.array([[10, 20], [60, 18], [62, 40], [11, 42]])]
    result = {"rec_polys": polys, "rec_texts": ["거래명세서"], "rec_scores": [0.97]}
    engine, _ = make_engine([result])

    page = engine.recognize(blank_image())

    assert (page.width, page.height) == (200, 100)
    assert len(page.tokens) == 1
    token = page.tokens[0]
    assert token.text == "거래명세서"
    assert token.bbox == (10.0, 18.0, 62.0, 42.0)
    assert token.confidence == pytest.approx(0.97)


def test_이미지_밖으로_나간_좌표는_경계로_자른다() -> None:
    polys = [np.array([[-5, -3], [210, -3], [210, 120], [-5, 120]])]
    engine, _ = make_engine([{"rec_polys": polys, "rec_texts": ["가"], "rec_scores": [0.5]}])

    token = engine.recognize(blank_image()).tokens[0]

    assert token.bbox == (0.0, 0.0, 200.0, 100.0)


def test_신뢰도는_0과_1_사이로_맞춘다() -> None:
    polys = [np.array([[0, 0], [5, 0], [5, 5], [0, 5]])] * 2
    engine, _ = make_engine(
        [{"rec_polys": polys, "rec_texts": ["a", "b"], "rec_scores": [1.0000001, -0.0000001]}]
    )

    confidences = [t.confidence for t in engine.recognize(blank_image()).tokens]

    assert confidences == [1.0, 0.0]


def test_빈_텍스트는_버린다() -> None:
    polys = [np.array([[0, 0], [5, 0], [5, 5], [0, 5]])] * 2
    engine, _ = make_engine(
        [{"rec_polys": polys, "rec_texts": ["", "  "], "rec_scores": [0.9, 0.9]}]
    )

    assert engine.recognize(blank_image()).tokens == ()


def test_인식_결과가_없으면_빈_페이지를_돌려준다() -> None:
    engine, _ = make_engine([])

    page = engine.recognize(blank_image(300, 150))

    assert (page.width, page.height, page.tokens) == (300, 150, ())


def test_결과_길이가_어긋나면_예외를_낸다() -> None:
    polys = [np.array([[0, 0], [5, 0], [5, 5], [0, 5]])]
    engine, _ = make_engine([{"rec_polys": polys, "rec_texts": ["a", "b"], "rec_scores": [0.9]}])

    with pytest.raises(ValueError, match="길이"):
        engine.recognize(blank_image())


def test_RGB가_아닌_입력은_거부한다() -> None:
    engine, _ = make_engine([])

    with pytest.raises(ValueError, match="RGB"):
        engine.recognize(np.zeros((10, 10), dtype=np.uint8))


def test_predictor에는_BGR로_바꿔_넘긴다() -> None:
    """PaddleOCR는 OpenCV 관례(BGR)로 배열을 받는다."""
    image = blank_image(4, 2)
    image[..., 0] = 255  # R 채널만 켠다
    image[..., 1:] = 0
    engine, predictor = make_engine([])

    engine.recognize(image)

    assert predictor.received[0][0, 0].tolist() == [0, 0, 255]


@pytest.mark.parametrize(
    ("environ", "expected"),
    [({}, False), ({"OCR_USE_GPU": "1"}, True), ({"OCR_USE_GPU": "true"}, True),
     ({"OCR_USE_GPU": "0"}, False), ({"OCR_USE_GPU": "off"}, False)],
)
def test_GPU_사용은_환경변수로_정한다(environ: dict[str, str], expected: bool) -> None:
    assert resolve_use_gpu(environ) is expected


def test_잘못된_GPU_환경변수는_예외를_낸다() -> None:
    with pytest.raises(ValueError, match="OCR_USE_GPU"):
        resolve_use_gpu({"OCR_USE_GPU": "maybe"})


def test_모듈을_import해도_모델을_로드하지_않고_레지스트리에_등록된다() -> None:
    assert "paddleocr" in registry.names()
    assert isinstance(registry, EngineRegistry)


@pytest.mark.slow
def test_골든셋_한_장을_실제_모델로_인식한다() -> None:
    from PIL import Image

    image = np.asarray(Image.open(GOLDEN_DIR / "invoice_000.png").convert("RGB"), dtype=np.uint8)
    engine = PaddleOcrEngine(predictor=build_paddleocr(use_gpu=False), use_gpu=False)

    page = engine.recognize(image)

    assert len(page.tokens) >= 10
    assert all(0.0 <= t.confidence <= 1.0 for t in page.tokens)
    assert all(
        0 <= t.bbox[0] <= t.bbox[2] <= page.width and 0 <= t.bbox[1] <= t.bbox[3] <= page.height
        for t in page.tokens
    )
    assert "거래명세서" in page.text.replace(" ", "")
