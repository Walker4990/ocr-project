"""표 구조 인식(PaddleOCR 3.x TableRecognitionPipelineV2). import만으로는 paddle을 로드하지 않는다.

흐름: 레이아웃 검출(PP-DocLayout-L)로 표 영역을 찾고, 영역마다 잘라 표 파이프라인
(셀 검출 + SLANeXt 구조 인식 + OCR)에 넣어 HTML과 셀 상자를 받아 `OcrTable`로 바꾼다.

파이프라인에 통째로 맡기지 않고 영역을 먼저 고르는 이유(골든셋 invoice_000, CPU 실측):
레이아웃을 켠 채 전체 이미지를 넣으면 같은 표와 페이지 전체를 감싼 표가 중복 검출돼
표 6개를 처리하느라 장당 약 40초가 걸린다(SLANeXt 30초). 페이지 전체를 하나의 표로 넣으면
구조 인식이 틀어져 HTML과 셀 상자의 짝이 어긋난다. 그래서 중복과 페이지 전체 상자를 걸러
영역별로 따로 넣는다.

좌표 규약은 OcrToken과 같다: 원본 이미지 픽셀, (x_min, y_min, x_max, y_max), 입력은 RGB.
"""

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Protocol, cast

import numpy as np
from numpy.typing import NDArray

from app.ocr.engine import BBox
from app.ocr.engines.paddleocr_adapter import resolve_use_gpu

logger = logging.getLogger(__name__)

LAYOUT_MODEL_NAME = "PP-DocLayout-L"
TABLE_LABEL = "table"
# 두 상자가 이 비율 넘게 겹치면 같은 표로 본다
_DUPLICATE_IOU = 0.7
# 상자 안에 다른 상자가 이 비율 이상 들어 있으면 "품고 있다"고 본다
_CONTAIN_RATIO = 0.9


class TableStructureError(ValueError):
    """표 HTML과 셀 상자가 맞지 않아 구조를 만들 수 없다."""


@dataclass(frozen=True)
class TableCell:
    row: int
    col: int
    row_span: int
    col_span: int
    text: str
    bbox: BBox


@dataclass(frozen=True)
class OcrTable:
    bbox: BBox
    n_rows: int
    n_cols: int
    cells: tuple[TableCell, ...]

    def grid(self) -> list[list[str]]:
        """n_rows x n_cols 격자. 병합 셀의 텍스트는 시작 칸에만 두고 나머지는 빈 문자열이다."""
        grid = [["" for _ in range(self.n_cols)] for _ in range(self.n_rows)]
        for cell in self.cells:
            grid[cell.row][cell.col] = cell.text
        return grid

    def rows(self) -> list[list[str]]:
        """행마다 그 행에서 시작하는 셀의 텍스트만 열 순서대로 모은다(병합으로 빈 칸 제외)."""
        by_row: dict[int, list[TableCell]] = {r: [] for r in range(self.n_rows)}
        for cell in self.cells:
            by_row[cell.row].append(cell)
        return [
            [c.text for c in sorted(by_row[r], key=lambda c: c.col)] for r in range(self.n_rows)
        ]


@dataclass(frozen=True)
class ParsedCell:
    row: int
    col: int
    row_span: int
    col_span: int
    text: str


class _TableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.cells: list[ParsedCell] = []
        self._row = -1
        self._col = 0
        self._occupied: set[tuple[int, int]] = set()
        self._in_cell = False
        self._row_span = 1
        self._col_span = 1
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row += 1
            self._col = 0
        elif tag in ("td", "th"):
            attr = dict(attrs)
            self._row_span = _span(attr.get("rowspan"))
            self._col_span = _span(attr.get("colspan"))
            self._in_cell = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag not in ("td", "th") or not self._in_cell:
            return
        self._in_cell = False
        # 윗줄 rowspan이 차지한 칸은 건너뛴다
        while (self._row, self._col) in self._occupied:
            self._col += 1
        for r in range(self._row, self._row + self._row_span):
            for c in range(self._col, self._col + self._col_span):
                self._occupied.add((r, c))
        text = " ".join("".join(self._parts).split())
        self.cells.append(ParsedCell(self._row, self._col, self._row_span, self._col_span, text))
        self._col += self._col_span


def _span(raw: str | None) -> int:
    try:
        return max(1, int(raw)) if raw is not None else 1
    except ValueError:
        return 1


def parse_table_html(html: str) -> list[ParsedCell]:
    """PaddleX가 돌려주는 표 HTML에서 셀(행·열·병합·텍스트)을 읽는다. 표가 없으면 빈 목록."""
    parser = _TableHtmlParser()
    parser.feed(html)
    parser.close()
    return parser.cells


def build_table(html: str, cell_boxes: Sequence[Any], offset: tuple[float, float]) -> OcrTable:
    """HTML 셀과 셀 상자를 순서대로 짝지어 표를 만든다. 상자에 offset을 더해 원본 좌표로 옮긴다."""
    parsed = parse_table_html(html)
    if not parsed:
        raise TableStructureError("HTML에 셀이 없다")
    if len(parsed) != len(cell_boxes):
        raise TableStructureError(
            f"HTML 셀 {len(parsed)}개와 셀 상자 {len(cell_boxes)}개가 맞지 않는다"
        )

    dx, dy = offset
    cells: list[TableCell] = []
    for cell, raw in zip(parsed, cell_boxes, strict=True):
        x_min, y_min, x_max, y_max = _rect(raw)
        cells.append(
            TableCell(
                row=cell.row,
                col=cell.col,
                row_span=cell.row_span,
                col_span=cell.col_span,
                text=cell.text,
                bbox=(x_min + dx, y_min + dy, x_max + dx, y_max + dy),
            )
        )
    return OcrTable(
        bbox=(
            min(c.bbox[0] for c in cells),
            min(c.bbox[1] for c in cells),
            max(c.bbox[2] for c in cells),
            max(c.bbox[3] for c in cells),
        ),
        n_rows=max(c.row + c.row_span for c in cells),
        n_cols=max(c.col + c.col_span for c in cells),
        cells=tuple(cells),
    )


def _rect(raw: Any) -> BBox:
    """상자 4값 또는 다각형 점들을 바깥 사각형으로 바꾼다. 좌표가 뒤집혀도 바로잡는다."""
    points = np.asarray(raw, dtype=np.float64)
    if points.size == 4:
        x0, y0, x1, y1 = points.reshape(4).tolist()
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    pairs = points.reshape(-1, 2)
    x_min, y_min = pairs.min(axis=0)
    x_max, y_max = pairs.max(axis=0)
    return (float(x_min), float(y_min), float(x_max), float(y_max))


def _area(box: BBox) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection(a: BBox, b: BBox) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def select_table_boxes(boxes: Sequence[BBox], max_tables: int | None = None) -> list[BBox]:
    """레이아웃이 낸 표 상자에서 중복과 다른 표를 둘 이상 품은 큰 상자(페이지 전체 등)를 걸러낸다.

    max_tables가 있으면 넓이가 큰 순으로 그 수만 남긴다. 결과는 위에서 아래, 왼쪽에서 오른쪽 순이다.
    """
    unique: list[BBox] = []
    for box in sorted(boxes, key=_area, reverse=True):
        if any(_iou(box, kept) > _DUPLICATE_IOU for kept in unique):
            continue
        unique.append(box)

    def holds_others(box: BBox) -> bool:
        inside = sum(
            1
            for other in unique
            if other is not box
            and _area(other) > 0
            and _intersection(box, other) / _area(other) >= _CONTAIN_RATIO
        )
        return inside >= 2

    selected = [box for box in unique if not holds_others(box)]
    if max_tables is not None:
        selected = sorted(selected, key=_area, reverse=True)[:max_tables]
    return sorted(selected, key=lambda b: (b[1], b[0]))


def _iou(a: BBox, b: BBox) -> float:
    inter = _intersection(a, b)
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


class LayoutPredictor(Protocol):
    """PaddleOCR LayoutDetection 중 쓰는 부분. 결과 항목은 {"boxes": [{"label", "coordinate"}]}."""

    def predict(self, image: NDArray[np.uint8]) -> Sequence[Mapping[str, Any]]: ...


class TablePipelinePredictor(Protocol):
    """TableRecognitionPipelineV2 중 쓰는 부분. 결과 항목은 {"table_res_list": [...]}."""

    def predict(self, image: NDArray[np.uint8]) -> Sequence[Mapping[str, Any]]: ...


class TableRecognizer:
    """표 영역 검출 -> 영역별 표 구조 인식. 모델은 한 번 만들어 워커에 상주시킨다."""

    def __init__(
        self,
        layout: LayoutPredictor,
        table_pipeline: TablePipelinePredictor,
        max_tables: int | None = None,
    ) -> None:
        self._layout = layout
        self._table_pipeline = table_pipeline
        self._max_tables = max_tables

    def recognize(self, image: NDArray[np.uint8]) -> tuple[OcrTable, ...]:
        """RGB 이미지(높이 x 너비 x 3) 한 장에서 표를 찾아 구조를 돌려준다. 표가 없으면 빈 튜플."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError(f"RGB 이미지(높이 x 너비 x 3)여야 한다: shape={image.shape}")
        height, width = int(image.shape[0]), int(image.shape[1])

        # PaddleOCR는 OpenCV 관례(BGR)로 받는다
        bgr = np.ascontiguousarray(image[..., ::-1])
        started = time.perf_counter()
        regions = self._find_table_regions(bgr, width, height)

        tables: list[OcrTable] = []
        for x_min, y_min, x_max, y_max in regions:
            crop = np.ascontiguousarray(bgr[y_min:y_max, x_min:x_max])
            table = self._recognize_region(crop, (float(x_min), float(y_min)))
            if table is not None:
                tables.append(table)
        logger.info(
            "표 인식 완료: %dx%d, 영역 %d개, 표 %d개, %.0fms",
            width, height, len(regions), len(tables), (time.perf_counter() - started) * 1000,
        )  # fmt: skip
        return tuple(tables)

    def _find_table_regions(
        self, bgr: NDArray[np.uint8], width: int, height: int
    ) -> list[tuple[int, int, int, int]]:
        raw_boxes: list[BBox] = []
        for result in self._layout.predict(bgr):
            for item in cast(Sequence[Mapping[str, Any]], result.get("boxes", [])):
                if item.get("label") == TABLE_LABEL:
                    raw_boxes.append(_rect(item["coordinate"]))

        regions: list[tuple[int, int, int, int]] = []
        for x0, y0, x1, y1 in select_table_boxes(raw_boxes, self._max_tables):
            region = (
                max(0, int(round(x0))),
                max(0, int(round(y0))),
                min(width, int(round(x1))),
                min(height, int(round(y1))),
            )
            if region[2] > region[0] and region[3] > region[1]:
                regions.append(region)
        return regions

    def _recognize_region(
        self, crop: NDArray[np.uint8], offset: tuple[float, float]
    ) -> OcrTable | None:
        for result in self._table_pipeline.predict(crop):
            tables = cast(Sequence[Mapping[str, Any]], result.get("table_res_list", []))
            if not tables:
                continue
            first = tables[0]
            try:
                return build_table(str(first["pred_html"]), first["cell_box_list"], offset)
            except TableStructureError as error:
                # 한 표가 어긋나도 나머지는 살린다. 조용히 삼키지 않고 기록한다
                logger.warning("표 구조를 만들지 못해 건너뛴다: offset=%s, %s", offset, error)
                return None
        return None


def build_table_recognizer(
    use_gpu: bool | None = None, max_tables: int | None = None
) -> TableRecognizer:
    """표 인식 모델을 로드한다(첫 호출에는 다운로드 포함, CPU 약 1~2분).

    use_gpu가 None이면 환경변수 OCR_USE_GPU를 따른다.
    paddlepaddle 3.2.2 CPU(oneDNN 켬)에서 동작을 확인했다.
    """
    gpu = resolve_use_gpu() if use_gpu is None else use_gpu
    device = "gpu" if gpu else "cpu"
    # 무거워서 실제로 만들 때만 import한다. 타입 스텁이 없다
    from paddleocr import (  # pyright: ignore[reportMissingTypeStubs]
        LayoutDetection,
        TableRecognitionPipelineV2,
    )

    layout = LayoutDetection(model_name=LAYOUT_MODEL_NAME, device=device)
    pipeline = TableRecognitionPipelineV2(
        device=device,
        # 인식 모델을 지정하지 않으면 중국어 모델이 쓰여 한글이 깨진다
        text_detection_model_name="PP-OCRv5_server_det" if gpu else "PP-OCRv5_mobile_det",
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        # 표 영역은 우리가 먼저 골라 잘라 넣는다(모듈 설명 참고)
        use_layout_detection=False,
    )
    return TableRecognizer(
        layout=cast(LayoutPredictor, layout),
        table_pipeline=cast(TablePipelinePredictor, pipeline),
        max_tables=max_tables,
    )
