"""표 구조 인식 테스트. 변환·그리드 로직은 가짜 predictor로, 실제 모델은 slow 마커로 검증한다."""

import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from app.ocr.table_recognizer import (
    BBox,
    OcrTable,
    TableCell,
    TableRecognizer,
    TableStructureError,
    build_table,
    build_table_recognizer,
    parse_table_html,
    select_table_boxes,
)

GOLDEN_DIR = Path(__file__).resolve().parents[4] / "samples" / "golden"

ITEM_HTML = (
    "<html><body><table><tbody>"
    "<tr><td>No</td><td>품목</td><td>수량</td></tr>"
    "<tr><td>1</td><td>클리어 파일</td><td>7</td></tr>"
    "</tbody></table></body></html>"
)


def grid_boxes(rows: int, cols: int, cell_w: float = 100, cell_h: float = 50) -> list[list[float]]:
    return [
        [c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h]
        for r in range(rows)
        for c in range(cols)
    ]


# --- HTML 파싱 ---


def test_html의_행과_열을_셀로_바꾼다() -> None:
    cells = parse_table_html(ITEM_HTML)

    assert [(c.row, c.col, c.text) for c in cells] == [
        (0, 0, "No"), (0, 1, "품목"), (0, 2, "수량"),
        (1, 0, "1"), (1, 1, "클리어 파일"), (1, 2, "7"),
    ]  # fmt: skip
    assert all(c.row_span == 1 and c.col_span == 1 for c in cells)


def test_colspan과_rowspan이_차지한_칸은_건너뛰고_열을_센다() -> None:
    html = (
        "<table>"
        '<tr><td colspan="2">제목</td><td rowspan="2">합</td></tr>'
        "<tr><td>a</td><td>b</td></tr>"
        "<tr><td>c</td><td>d</td><td>e</td></tr>"
        "</table>"
    )

    cells = parse_table_html(html)

    by_text = {c.text: c for c in cells}
    assert (by_text["제목"].row, by_text["제목"].col, by_text["제목"].col_span) == (0, 0, 2)
    assert (by_text["합"].col, by_text["합"].row_span) == (2, 2)
    # 둘째 줄은 rowspan이 셋째 열을 차지하므로 a, b가 0, 1열에 들어간다
    assert (by_text["a"].row, by_text["a"].col) == (1, 0)
    assert (by_text["b"].row, by_text["b"].col) == (1, 1)
    assert (by_text["e"].row, by_text["e"].col) == (2, 2)


def test_셀_텍스트의_앞뒤_공백과_줄바꿈을_정리한다() -> None:
    cells = parse_table_html("<table><tr><td>\n 대표\n자 </td><td></td></tr></table>")

    assert [c.text for c in cells] == ["대표 자", ""]


def test_표가_없는_html은_빈_목록이다() -> None:
    assert parse_table_html("<html><body></body></html>") == []


# --- 표 구성 ---


def test_html_셀과_셀_상자를_순서대로_짝짓고_좌표를_원본으로_옮긴다() -> None:
    boxes = grid_boxes(2, 3)

    table = build_table(ITEM_HTML, boxes, offset=(1000.0, 200.0))

    assert (table.n_rows, table.n_cols) == (2, 3)
    assert table.cells[4].text == "클리어 파일"
    assert table.cells[4].bbox == (1100.0, 250.0, 1200.0, 300.0)
    assert table.bbox == (1000.0, 200.0, 1300.0, 300.0)


def test_셀_수와_상자_수가_다르면_예외를_낸다() -> None:
    with pytest.raises(TableStructureError, match="셀"):
        build_table(ITEM_HTML, grid_boxes(2, 2), offset=(0.0, 0.0))


def test_상자_좌표가_뒤집히면_보정한다() -> None:
    html = "<table><tr><td>a</td></tr></table>"

    table = build_table(html, [[50.0, 40.0, 10.0, 5.0]], offset=(0.0, 0.0))

    assert table.cells[0].bbox == (10.0, 5.0, 50.0, 40.0)


def test_grid는_병합_셀의_시작_칸에만_텍스트를_둔다() -> None:
    table = OcrTable(
        bbox=(0.0, 0.0, 30.0, 20.0),
        n_rows=2,
        n_cols=3,
        cells=(
            TableCell(0, 0, 1, 2, "제목", (0.0, 0.0, 20.0, 10.0)),
            TableCell(0, 2, 2, 1, "합", (20.0, 0.0, 30.0, 20.0)),
            TableCell(1, 0, 1, 1, "a", (0.0, 10.0, 10.0, 20.0)),
            TableCell(1, 1, 1, 1, "b", (10.0, 10.0, 20.0, 20.0)),
        ),
    )

    assert table.grid() == [["제목", "", "합"], ["a", "b", ""]]
    assert table.rows() == [["제목", "합"], ["a", "b"]]


# --- 표 영역 고르기 ---


def test_겹치는_중복_상자를_하나로_줄인다() -> None:
    boxes: list[BBox] = [(109, 318, 809, 669), (110, 319, 808, 668)]

    assert len(select_table_boxes(boxes)) == 1


def test_다른_표를_둘_이상_품은_큰_상자는_버린다() -> None:
    page: BBox = (105, 310, 1546, 1388)
    boxes: list[BBox] = [
        (109, 318, 809, 669), (847, 317, 1545, 670), (108, 717, 1544, 1220), page,
    ]  # fmt: skip

    selected = select_table_boxes(boxes)

    assert page not in selected
    assert len(selected) == 3


def test_상자는_위에서_아래로_왼쪽에서_오른쪽으로_정렬한다() -> None:
    boxes: list[BBox] = [(0, 500, 100, 600), (200, 0, 300, 100), (0, 0, 100, 100)]

    assert select_table_boxes(boxes) == [(0, 0, 100, 100), (200, 0, 300, 100), (0, 500, 100, 600)]


def test_max_tables는_넓이가_큰_표부터_남긴다() -> None:
    boxes: list[BBox] = [(0, 0, 10, 10), (0, 100, 500, 400), (0, 500, 100, 600)]

    assert select_table_boxes(boxes, max_tables=1) == [(0, 100, 500, 400)]


# --- 인식기 ---


class FakeLayout:
    def __init__(self, boxes: Sequence[tuple[str, Sequence[float]]]) -> None:
        self._boxes = boxes

    def predict(self, image: NDArray[np.uint8]) -> list[Mapping[str, Any]]:
        return [
            {"boxes": [{"label": label, "coordinate": list(c), "score": 0.9}
                       for label, c in self._boxes]}
        ]  # fmt: skip


class FakeTablePipeline:
    def __init__(self, html: str, cell_boxes: list[list[float]]) -> None:
        self._html = html
        self._cell_boxes = cell_boxes
        self.received: list[NDArray[np.uint8]] = []

    def predict(self, image: NDArray[np.uint8]) -> list[Mapping[str, Any]]:
        self.received.append(image)
        return [{"table_res_list": [{"pred_html": self._html, "cell_box_list": self._cell_boxes}]}]


def blank_image(width: int = 400, height: int = 300) -> NDArray[np.uint8]:
    return np.full((height, width, 3), 255, dtype=np.uint8)


def test_레이아웃의_표_영역을_잘라_표_파이프라인에_넘기고_좌표를_원본으로_옮긴다() -> None:
    layout = FakeLayout([("table", (50, 100, 350, 200)), ("table_title", (0, 0, 40, 40))])
    pipeline = FakeTablePipeline(ITEM_HTML, grid_boxes(2, 3))
    recognizer = TableRecognizer(layout=layout, table_pipeline=pipeline)

    tables = recognizer.recognize(blank_image())

    assert len(tables) == 1
    assert pipeline.received[0].shape == (100, 300, 3)
    assert tables[0].cells[4].text == "클리어 파일"
    assert tables[0].cells[4].bbox == (150.0, 150.0, 250.0, 200.0)


def test_표_파이프라인에는_BGR로_바꿔_넘긴다() -> None:
    image = blank_image(400, 300)
    image[..., 0] = 255
    image[..., 1:] = 0
    pipeline = FakeTablePipeline(ITEM_HTML, grid_boxes(2, 3))
    recognizer = TableRecognizer(
        layout=FakeLayout([("table", (0, 0, 100, 100))]), table_pipeline=pipeline
    )

    recognizer.recognize(image)

    assert pipeline.received[0][0, 0].tolist() == [0, 0, 255]


def test_표_영역이_없으면_빈_목록을_돌려준다() -> None:
    pipeline = FakeTablePipeline(ITEM_HTML, grid_boxes(2, 3))
    recognizer = TableRecognizer(
        layout=FakeLayout([("text", (0, 0, 10, 10))]), table_pipeline=pipeline
    )

    assert recognizer.recognize(blank_image()) == ()
    assert pipeline.received == []


def test_구조가_어긋난_표는_건너뛰고_나머지를_돌려준다() -> None:
    layout = FakeLayout([("table", (0, 0, 100, 100)), ("table", (0, 150, 100, 250))])

    class Flaky(FakeTablePipeline):
        def predict(self, image: NDArray[np.uint8]) -> list[Mapping[str, Any]]:
            self.received.append(image)
            boxes = grid_boxes(2, 2) if len(self.received) == 1 else grid_boxes(2, 3)
            return [{"table_res_list": [{"pred_html": ITEM_HTML, "cell_box_list": boxes}]}]

    recognizer = TableRecognizer(layout=layout, table_pipeline=Flaky(ITEM_HTML, []))

    tables = recognizer.recognize(blank_image())

    assert len(tables) == 1
    assert tables[0].bbox[1] == 150.0


def test_이미지_가장자리를_넘는_표_영역은_경계로_자른다() -> None:
    layout = FakeLayout([("table", (-10, -10, 500, 400))])
    pipeline = FakeTablePipeline(ITEM_HTML, grid_boxes(2, 3))
    recognizer = TableRecognizer(layout=layout, table_pipeline=pipeline)

    recognizer.recognize(blank_image(400, 300))

    assert pipeline.received[0].shape == (300, 400, 3)


def test_RGB가_아닌_입력은_거부한다() -> None:
    recognizer = TableRecognizer(
        layout=FakeLayout([]), table_pipeline=FakeTablePipeline(ITEM_HTML, [])
    )

    with pytest.raises(ValueError, match="RGB"):
        recognizer.recognize(np.zeros((10, 10), dtype=np.uint8))


def test_모듈을_import해도_paddle을_import하지_않는다() -> None:
    code = (
        "import sys; import app.ocr.table_recognizer; "
        "sys.exit(1 if any(m == 'paddle' or m.startswith('paddleocr') "
        "or m.startswith('paddlex') for m in sys.modules) else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], check=False)
    assert result.returncode == 0


@pytest.mark.slow
def test_골든셋_한_장의_품목_표를_실제_모델로_읽는다() -> None:
    import json

    from PIL import Image

    image = np.asarray(Image.open(GOLDEN_DIR / "invoice_000.png").convert("RGB"), dtype=np.uint8)
    label = json.loads((GOLDEN_DIR / "invoice_000.json").read_text(encoding="utf-8"))
    expected_rows = len(label["invoice"]["items"])
    recognizer = build_table_recognizer(use_gpu=False)

    tables = recognizer.recognize(image)

    item_tables = [t for t in tables if t.n_rows == expected_rows + 1 and t.n_cols == 6]
    assert item_tables, f"품목 표를 찾지 못했다: {[(t.n_rows, t.n_cols) for t in tables]}"
    header = [c.text for c in item_tables[0].cells[:6]]
    assert header == ["No", "품목", "규격", "수량", "단가", "금액"]
    assert all(
        0 <= t.bbox[0] <= t.bbox[2] <= image.shape[1]
        and 0 <= t.bbox[1] <= t.bbox[3] <= image.shape[0]
        for t in tables
    )
