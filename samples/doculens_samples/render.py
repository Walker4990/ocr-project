"""Pillow로 거래명세서 양식 5종을 그린다. 같은 입력이면 항상 같은 이미지가 나온다."""
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
HEADER_FILL = (235, 235, 235)

FontName = Literal["gothic", "gothic_bold", "myeongjo", "coding"]
FONT_FILES: dict[FontName, str] = {
    "gothic": "NanumGothic-Regular.ttf",
    "gothic_bold": "NanumGothic-Bold.ttf",
    "myeongjo": "NanumMyeongjo-Regular.ttf",
    "coding": "NanumGothicCoding-Regular.ttf",
}

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
    def __init__(self, style: TemplateStyle) -> None:
        self.style = style
        self.image = Image.new("RGB", PAGE_SIZE, "white")
        self.draw = ImageDraw.Draw(self.image)
        self.body = _font(style.body_font, 30)
        self.bold = _font("gothic_bold", 30)

    def text(
        self, x: int, y: int, value: str, *, bold: bool = False, align: str = "l", width: int = 0
    ) -> None:
        font = self.bold if bold else self.body
        text_width = int(self.draw.textlength(value, font=font))
        if align == "r":
            x = x + width - 14 - text_width
        elif align == "c":
            x = x + (width - text_width) // 2
        else:
            x += 14
        self.draw.text((x, y + 13), value, font=font, fill=(0, 0, 0))

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
    c.text(MARGIN, underline_y + 20, f"문서번호: {invoice.document_no}")
    c.text(PAGE_SIZE[0] - MARGIN - 500, underline_y + 20, f"작성일자: {date_text}")
    return underline_y + 110


def _party_rows(party: Party) -> list[tuple[str, str]]:
    return [
        ("상호", party.name),
        ("등록번호", party.business_number),
        ("대표자", party.representative),
        ("주소", party.address),
    ]


def _draw_party(c: _Canvas, x: int, y: int, w: int, label: str, party: Party) -> int:
    label_w = 170
    c.box(x, y, w, ROW_HEIGHT, fill=HEADER_FILL)
    c.text(x, y, label, bold=True, align="c", width=w)
    y += ROW_HEIGHT
    for key, value in _party_rows(party):
        c.box(x, y, label_w, ROW_HEIGHT)
        c.box(x + label_w, y, w - label_w, ROW_HEIGHT)
        c.text(x, y, key, align="c", width=label_w)
        c.text(x + label_w, y, value)
        y += ROW_HEIGHT
    return y


def _draw_parties(c: _Canvas, invoice: Invoice, y: int) -> int:
    inner = PAGE_SIZE[0] - 2 * MARGIN
    if c.style.parties == "side_by_side":
        gap = 40
        w = (inner - gap) // 2
        end = _draw_party(c, MARGIN, y, w, "공급자", invoice.supplier)
        _draw_party(c, MARGIN + w + gap, y, w, "공급받는자", invoice.buyer)
        return end + 50
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
        c.text(x, y + ROW_HEIGHT, _won(value), bold=label == "합계금액", align="r", width=w)
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
        for (_, _, align), w, value in zip(columns, widths, cells, strict=True):
            if c.style.table == "grid" or header:
                c.box(x, row_y, w, ROW_HEIGHT, fill=fill)
            elif fill is not None:
                c.draw.rectangle((x, row_y, x + w, row_y + ROW_HEIGHT), fill=fill)
            c.text(x, row_y, value, bold=header, align="c" if header else align, width=w)
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


def render_invoice(invoice: Invoice, template_id: str) -> Image.Image:
    style = TEMPLATES.get(template_id)
    if style is None:
        raise ValueError(f"unknown template: {template_id}")
    canvas = _Canvas(style)
    y = _draw_title(canvas, invoice, MARGIN)
    y = _draw_parties(canvas, invoice, y)
    if style.totals_on_top:
        y = _draw_totals(canvas, invoice, y)
        _draw_items(canvas, invoice, y)
    else:
        y = _draw_items(canvas, invoice, y)
        _draw_totals(canvas, invoice, y)
    return canvas.image
