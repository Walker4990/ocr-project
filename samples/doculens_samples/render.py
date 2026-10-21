"""Pillow로 거래명세서 양식 5종을 그린다. 같은 입력이면 항상 같은 이미지가 나온다."""
import random
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

from doculens_samples.schema import Invoice, Party

PAGE_SIZE = (1654, 2339)  # A4, 200dpi
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
MARGIN = 110
ROW_HEIGHT = 62
LINE_HEIGHT = 42  # 칸 안에서 줄바꿈된 두 번째 줄부터 더해지는 높이
CELL_PADDING = 14
HEADER_FILL = (235, 235, 235)

FontName = Literal[
    "gothic", "gothic_bold", "myeongjo", "coding", "pen", "gaegu", "poorstory", "singleday"
]
FONT_FILES: dict[FontName, str] = {
    "gothic": "NanumGothic-Regular.ttf",
    "gothic_bold": "NanumGothic-Bold.ttf",
    "myeongjo": "NanumMyeongjo-Regular.ttf",
    "coding": "NanumGothicCoding-Regular.ttf",
    "pen": "NanumPenScript-Regular.ttf",
    "gaegu": "Gaegu-Regular.ttf",
    "poorstory": "PoorStory-Regular.ttf",
    "singleday": "SingleDay-Regular.ttf",
}

# 손글씨 모사용 (폰트, 크기). 폰트마다 같은 크기에서 글자 크기가 달라 따로 맞춘다
HAND_FONTS: tuple[tuple[FontName, int], ...] = (
    ("pen", 40),
    ("gaegu", 34),
    ("poorstory", 32),
    ("singleday", 34),
)
HAND_INKS: tuple[tuple[int, int, int], ...] = ((20, 30, 110), (15, 15, 15), (30, 60, 140))

Color = tuple[int, int, int]


@dataclass(frozen=True)
class TemplateStyle:
    title: str
    body_font: FontName
    parties: Literal["side_by_side", "stacked"]
    table: Literal["grid", "lines", "zebra"]
    accent: Color
    show_spec: bool
    totals_on_top: bool
    long_date: bool


TEMPLATES: dict[str, TemplateStyle] = {
    "classic": TemplateStyle(
        "거 래 명 세 서", "gothic", "side_by_side", "grid", (0, 0, 0), True, False, False
    ),
    "blue_stacked": TemplateStyle(
        "거래명세서", "gothic", "stacked", "zebra", (30, 70, 150), True, False, True
    ),
    "serif_simple": TemplateStyle(
        "거 래 명 세 표", "myeongjo", "side_by_side", "lines", (60, 60, 60), False, False, True
    ),
    "red_totals_top": TemplateStyle(
        "거래 명세서 (공급자 보관용)", "gothic", "stacked", "grid", (170, 30, 30), True, True, False
    ),
    "mono_receipt": TemplateStyle(
        "TRANSACTION 거래명세서", "coding", "side_by_side", "lines", (0, 90, 60), False, True, True
    ),
}
TEMPLATE_IDS: tuple[str, ...] = tuple(TEMPLATES)


@cache
def _font(name: FontName, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / FONT_FILES[name]
    if not path.exists():
        raise FileNotFoundError(f"{path} 없음. `python samples/fetch_fonts.py`로 폰트를 받는다")
    return ImageFont.truetype(str(path), size)


def _won(value: int) -> str:
    return f"{value:,}"


class _Canvas:
    def __init__(self, style: TemplateStyle, handwriting_seed: int | None = None) -> None:
        self.style = style
        self.image = Image.new("RGB", PAGE_SIZE, "white")
        self.draw = ImageDraw.Draw(self.image)
        self.body = _font(style.body_font, 30)
        self.bold = _font("gothic_bold", 30)
        self.overflows: list[str] = []
        self.rng = random.Random(handwriting_seed)
        self.handwritten = handwriting_seed is not None
        hand_name, hand_size = self.rng.choice(HAND_FONTS)
        self.hand_size = hand_size
        self.ink = self.rng.choice(HAND_INKS)
        # 기입란 값에 쓰는 글꼴. 손글씨 모드가 아니면 본문 글꼴과 같다
        self.value_font = _font(hand_name, hand_size) if self.handwritten else self.body

    def text(
        self,
        x: int,
        y: int,
        value: str,
        *,
        bold: bool = False,
        align: str = "l",
        width: int = 0,
        field: bool = False,
    ) -> None:
        """`field`는 값이 들어가는 기입란이다. 손글씨 모드에서는 이 글자만 손글씨체로 쓴다."""
        handwrite = field and self.handwritten
        font = self.value_font if handwrite else self.bold if bold else self.body
        text_width = int(self.draw.textlength(value, font=font))
        if width and text_width + CELL_PADDING * 2 > width:
            self.overflows.append(value)
        if align == "r":
            x = x + width - 14 - text_width
        elif align == "c":
            x = x + (width - text_width) // 2
        else:
            x += 14
        if handwrite:
            self._handwrite(x, y + 13, value)
        else:
            self.draw.text((x, y + 13), value, font=font, fill=(0, 0, 0))

    def _handwrite(self, x: int, y: int, value: str) -> None:
        """글자마다 위치, 기울기를 조금씩 흔들어 사람이 쓴 느낌을 낸다."""
        pad = self.hand_size
        cursor = float(x)
        for char in value:
            advance = self.draw.textlength(char, font=self.value_font)
            if char != " ":
                layer = Image.new("RGBA", (pad * 3, pad * 3), (0, 0, 0, 0))
                ImageDraw.Draw(layer).text(
                    (pad, pad), char, font=self.value_font, fill=(*self.ink, 255)
                )
                layer = layer.rotate(
                    self.rng.uniform(-4.0, 4.0), resample=Image.Resampling.BICUBIC
                )
                dx = self.rng.uniform(-1.5, 1.5)
                dy = self.rng.uniform(-3.0, 3.0)
                self.image.paste(layer, (round(cursor + dx - pad), round(y + dy - pad)), layer)
            cursor += advance + self.rng.uniform(-1.0, 2.0)

    def box(self, x: int, y: int, w: int, h: int, fill: Color | None = None) -> None:
        self.draw.rectangle((x, y, x + w, y + h), outline=self.style.accent, fill=fill, width=2)


def _draw_title(c: _Canvas, invoice: Invoice, y: int) -> int:
    font = _font("gothic_bold", 72)
    title_width = c.draw.textlength(c.style.title, font=font)
    c.draw.text(
        ((PAGE_SIZE[0] - title_width) // 2, y), c.style.title, font=font, fill=c.style.accent
    )
    underline_y = y + 100
    c.draw.line((MARGIN, underline_y, PAGE_SIZE[0] - MARGIN, underline_y), c.style.accent, 4)
    d = invoice.issue_date
    date_text = f"{d.year}년 {d.month:02d}월 {d.day:02d}일" if c.style.long_date else d.isoformat()
    _draw_labeled(c, MARGIN, underline_y + 20, "문서번호:", invoice.document_no)
    _draw_labeled(c, PAGE_SIZE[0] - MARGIN - 500, underline_y + 20, "작성일자:", date_text)
    return underline_y + 110


def _draw_labeled(c: _Canvas, x: int, y: int, label: str, value: str) -> None:
    if not c.handwritten:
        c.text(x, y, f"{label} {value}")
        return
    c.text(x, y, label)
    label_width = int(c.draw.textlength(label, font=c.body))
    c.text(x + label_width + 10, y, value, field=True)


def _party_rows(party: Party) -> list[tuple[str, str]]:
    return [
        ("상호", party.name),
        ("등록번호", party.business_number),
        ("대표자", party.representative),
        ("주소", party.address),
    ]


def _wrap(c: _Canvas, value: str, max_width: int) -> list[str]:
    """공백 단위로 줄바꿈하고, 공백 없이 너무 긴 단어는 글자 단위로 자른다."""
    lines: list[str] = []
    current = ""
    for word in value.split(" "):
        trial = f"{current} {word}".strip()
        if c.draw.textlength(trial, font=c.value_font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = ""
        for char in word:
            if c.draw.textlength(current + char, font=c.value_font) > max_width:
                lines.append(current)
                current = char
            else:
                current += char
    lines.append(current)
    return lines


def _draw_party(c: _Canvas, x: int, y: int, w: int, label: str, party: Party) -> int:
    label_w = 170
    value_w = w - label_w
    c.box(x, y, w, ROW_HEIGHT, fill=HEADER_FILL)
    c.text(x, y, label, bold=True, align="c", width=w)
    y += ROW_HEIGHT
    for key, value in _party_rows(party):
        lines = _wrap(c, value, value_w - CELL_PADDING * 2)
        row_height = ROW_HEIGHT + (len(lines) - 1) * LINE_HEIGHT
        c.box(x, y, label_w, row_height)
        c.box(x + label_w, y, value_w, row_height)
        c.text(x, y, key, align="c", width=label_w)
        for index, line in enumerate(lines):
            c.text(x + label_w, y + index * LINE_HEIGHT, line, width=value_w, field=True)
        y += row_height
    return y


def _draw_parties(c: _Canvas, invoice: Invoice, y: int) -> int:
    inner = PAGE_SIZE[0] - 2 * MARGIN
    if c.style.parties == "side_by_side":
        gap = 40
        w = (inner - gap) // 2
        left_end = _draw_party(c, MARGIN, y, w, "공급자", invoice.supplier)
        right_end = _draw_party(c, MARGIN + w + gap, y, w, "공급받는자", invoice.buyer)
        return max(left_end, right_end) + 50
    end = _draw_party(c, MARGIN, y, inner, "공급자", invoice.supplier)
    end = _draw_party(c, MARGIN, end + 30, inner, "공급받는자", invoice.buyer)
    return end + 50


def _draw_totals(c: _Canvas, invoice: Invoice, y: int) -> int:
    inner = PAGE_SIZE[0] - 2 * MARGIN
    cells = [
        ("공급가액", invoice.supply_amount),
        ("세액", invoice.tax_amount),
        ("합계금액", invoice.total_amount),
    ]
    w = inner // 3
    for i, (label, value) in enumerate(cells):
        x = MARGIN + i * w
        c.box(x, y, w, ROW_HEIGHT, fill=HEADER_FILL)
        c.box(x, y + ROW_HEIGHT, w, ROW_HEIGHT)
        c.text(x, y, label, bold=True, align="c", width=w)
        c.text(
            x, y + ROW_HEIGHT, _won(value), bold=label == "합계금액", align="r", width=w, field=True
        )
    return y + ROW_HEIGHT * 2 + 50


def _draw_items(c: _Canvas, invoice: Invoice, y: int) -> int:
    inner = PAGE_SIZE[0] - 2 * MARGIN
    columns = [("No", 0.06, "c"), ("품목", 0.36, "l")]
    if c.style.show_spec:
        columns.append(("규격", 0.16, "l"))
    columns += [("수량", 0.10, "r"), ("단가", 0.15, "r"), ("금액", 0.17, "r")]
    scale = inner / sum(share for _, share, _ in columns)
    widths = [int(share * scale) for _, share, _ in columns]

    max_rows = (PAGE_SIZE[1] - MARGIN - 300 - y) // ROW_HEIGHT - 1
    if len(invoice.items) > max_rows:
        raise ValueError(f"품목이 너무 많다: {len(invoice.items)} > {max_rows}")

    def draw_row(row_y: int, cells: list[str], header: bool, fill: Color | None) -> None:
        x = MARGIN
        for column, ((_, _, align), w, value) in enumerate(
            zip(columns, widths, cells, strict=True)
        ):
            if c.style.table == "grid" or header:
                c.box(x, row_y, w, ROW_HEIGHT, fill=fill)
            elif fill is not None:
                c.draw.rectangle((x, row_y, x + w, row_y + ROW_HEIGHT), fill=fill)
            # No 열(0번)은 인쇄된 일련번호라 손글씨로 쓰지 않는다
            c.text(
                x,
                row_y,
                value,
                bold=header,
                align="c" if header else align,
                width=w,
                field=not header and column > 0,
            )
            x += w
        if c.style.table == "lines" and not header:
            line_y = row_y + ROW_HEIGHT
            c.draw.line((MARGIN, line_y, MARGIN + inner, line_y), c.style.accent, 2)

    draw_row(y, [title for title, _, _ in columns], True, HEADER_FILL)
    y += ROW_HEIGHT
    for index, item in enumerate(invoice.items, start=1):
        cells = [str(index), item.name]
        if c.style.show_spec:
            cells.append(item.spec)
        cells += [_won(item.quantity), _won(item.unit_price), _won(item.amount)]
        zebra = (245, 247, 252) if c.style.table == "zebra" and index % 2 == 0 else None
        draw_row(y, cells, False, zebra)
        y += ROW_HEIGHT
    return y + 50


def _render(invoice: Invoice, template_id: str, handwriting_seed: int | None) -> _Canvas:
    style = TEMPLATES.get(template_id)
    if style is None:
        raise ValueError(f"unknown template: {template_id}")
    canvas = _Canvas(style, handwriting_seed)
    y = _draw_title(canvas, invoice, MARGIN)
    y = _draw_parties(canvas, invoice, y)
    if style.totals_on_top:
        y = _draw_totals(canvas, invoice, y)
        _draw_items(canvas, invoice, y)
    else:
        y = _draw_items(canvas, invoice, y)
        _draw_totals(canvas, invoice, y)
    return canvas


def render_invoice(
    invoice: Invoice, template_id: str, *, handwriting_seed: int | None = None
) -> Image.Image:
    """`handwriting_seed`를 주면 기입란 값을 손글씨체로 흉내 내어 쓴다(실제 필기는 아니다)."""
    return _render(invoice, template_id, handwriting_seed).image


def find_overflows(
    invoice: Invoice, template_id: str, *, handwriting_seed: int | None = None
) -> list[str]:
    """칸 너비를 넘겨 그려진 글자 목록. 비어 있어야 정상이다."""
    return _render(invoice, template_id, handwriting_seed).overflows
