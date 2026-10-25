"""Tesseract 어댑터 테스트. 변환 로직은 가짜 러너로, 실제 바이너리는 있을 때만 검증한다."""
import shutil
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray

from app.ocr.engine import OcrEngine, registry
from app.ocr.engines.tesseract_adapter import (
    DEFAULT_LANG,
    TesseractData,
    TesseractEngine,
    build_tesseract,
)

GOLDEN_DIR = Path(__file__).resolve().parents[4] / "samples" / "golden"


class FakeRunner:
    def __init__(self, data: TesseractData) -> None:
        self._data = data
        self.received: list[NDArray[np.uint8]] = []

    def image_to_data(self, image: NDArray[np.uint8]) -> TesseractData:
        self.received.append(image)
        return self._data


def blank_image(width: int = 200, height: int = 100) -> NDArray[np.uint8]:
    return np.full((height, width, 3), 255, dtype=np.uint8)


Row = tuple[int, int, int, int, int, int, int, int, float, str]


def make_data(rows: list[Row]) -> TesseractData:
    """행: (level, block, par, line, left, top, width, height, conf, text)"""
    return {
        "level": [r[0] for r in rows],
        "block_num": [r[1] for r in rows],
        "par_num": [r[2] for r in rows],
        "line_num": [r[3] for r in rows],
        "left": [r[4] for r in rows],
        "top": [r[5] for r in rows],
        "width": [r[6] for r in rows],
        "height": [r[7] for r in rows],
        "conf": [r[8] for r in rows],
        "text": [r[9] for r in rows],
    }


def make_engine(data: TesseractData) -> tuple[TesseractEngine, FakeRunner]:
    runner = FakeRunner(data)
    return TesseractEngine(runner=runner), runner


def test_엔진_프로토콜을_만족한다() -> None:
    engine, _ = make_engine(make_data([]))
    assert isinstance(engine, OcrEngine)
    assert engine.name == "tesseract"
    assert engine.supports_gpu is False


def test_같은_줄의_단어를_한_토큰으로_합친다() -> None:
    data = make_data(
        [
            (5, 1, 1, 1, 10, 20, 30, 12, 90.0, "합계"),
            (5, 1, 1, 1, 50, 18, 40, 16, 70.0, "금액"),
            (5, 1, 1, 2, 10, 50, 60, 12, 80.0, "다음줄"),
        ]
    )
    engine, _ = make_engine(data)

    page = engine.recognize(blank_image())

    assert (page.width, page.height) == (200, 100)
    assert [t.text for t in page.tokens] == ["합계 금액", "다음줄"]
    first = page.tokens[0]
    assert first.bbox == (10.0, 18.0, 90.0, 34.0)
    assert first.confidence == pytest.approx(0.8)


def test_신뢰도를_0에서_1로_바꾼다() -> None:
    engine, _ = make_engine(make_data([(5, 1, 1, 1, 0, 0, 10, 10, 100.0, "가")]))
    assert engine.recognize(blank_image()).tokens[0].confidence == pytest.approx(1.0)


def test_빈_텍스트와_음수_신뢰도_단어는_버린다() -> None:
    data = make_data(
        [
            (4, 1, 1, 1, 0, 0, 100, 10, -1.0, ""),
            (5, 1, 1, 1, 0, 0, 10, 10, -1.0, "   "),
            (5, 1, 1, 1, 20, 0, 10, 10, 85.0, "가"),
        ]
    )
    engine, _ = make_engine(data)

    tokens = engine.recognize(blank_image()).tokens

    assert [t.text for t in tokens] == ["가"]


def test_이미지_밖으로_나간_좌표는_경계로_자른다() -> None:
    engine, _ = make_engine(make_data([(5, 1, 1, 1, -5, -3, 220, 130, 50.0, "가")]))
    assert engine.recognize(blank_image()).tokens[0].bbox == (0.0, 0.0, 200.0, 100.0)


def test_RGB가_아닌_입력은_거부한다() -> None:
    engine, _ = make_engine(make_data([]))
    with pytest.raises(ValueError):
        engine.recognize(np.zeros((10, 10), dtype=np.uint8))


def test_러너에는_RGB_원본을_넘긴다() -> None:
    engine, runner = make_engine(make_data([]))
    image = blank_image()
    image[0, 0] = (1, 2, 3)

    engine.recognize(image)

    assert tuple(runner.received[0][0, 0]) == (1, 2, 3)


def test_레지스트리에_등록되어_있다() -> None:
    import app.ocr.engines  # noqa: F401  # pyright: ignore[reportUnusedImport]

    assert "tesseract" in registry.names()


def test_기본_언어는_한국어와_영어다() -> None:
    assert DEFAULT_LANG == "kor+eng"


def test_바이너리가_없으면_설치_안내가_담긴_오류를_낸다(monkeypatch: pytest.MonkeyPatch) -> None:

    def no_which(_name: str) -> None:
        return None

    def no_file(_path: str) -> bool:
        return False

    monkeypatch.setattr("shutil.which", no_which)
    monkeypatch.setattr("os.path.isfile", no_file)
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    with pytest.raises(RuntimeError, match="Tesseract"):
        build_tesseract()


def _tesseract_ready() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # pyright: ignore[reportMissingTypeStubs]

        languages = cast(list[str], pytesseract.get_languages())  # pyright: ignore[reportUnknownMemberType]
    except Exception:
        return False
    return {"kor", "eng"} <= set(languages)


@pytest.mark.slow
@pytest.mark.skipif(not _tesseract_ready(), reason="Tesseract 바이너리 또는 kor 학습 데이터가 없다")
def test_실제_Tesseract로_골든셋_헤더를_읽는다() -> None:
    from app.ocr.preprocessing import decode_image

    path = GOLDEN_DIR / "invoice_000.png"
    page = TesseractEngine(runner=build_tesseract()).recognize(
        decode_image(path.read_bytes())
    )

    assert page.tokens
    assert "거래명세서" in page.text.replace(" ", "")
