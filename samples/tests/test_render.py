"""거래명세서 템플릿 렌더링 테스트."""
import numpy as np
import pytest
from doculens_samples.data import generate_invoice
from doculens_samples.render import PAGE_SIZE, TEMPLATE_IDS, find_overflows, render_invoice
from doculens_samples.schema import Invoice
from PIL import Image, ImageChops


def test_has_at_least_five_templates() -> None:
    assert len(set(TEMPLATE_IDS)) >= 5


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_render_returns_rgb_page_image(invoice: Invoice, template_id: str) -> None:
    image = render_invoice(invoice, template_id)
    assert image.mode == "RGB"
    assert image.size == PAGE_SIZE


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_render_is_not_blank(invoice: Invoice, template_id: str) -> None:
    image = render_invoice(invoice, template_id)
    assert np.asarray(image.convert("L")).min() < 100


def test_templates_look_different(invoice: Invoice) -> None:
    images = [render_invoice(invoice, t) for t in TEMPLATE_IDS]
    for i, a in enumerate(images):
        for b in images[i + 1 :]:
            assert ImageChops.difference(a, b).getbbox() is not None


def test_render_is_deterministic(invoice: Invoice) -> None:
    first = render_invoice(invoice, TEMPLATE_IDS[0])
    second = render_invoice(invoice, TEMPLATE_IDS[0])
    assert ImageChops.difference(first, second).getbbox() is None


def test_more_items_changes_image(invoice: Invoice) -> None:
    longer = invoice.model_copy(update={"items": invoice.items * 4})
    a = render_invoice(invoice, TEMPLATE_IDS[0])
    b = render_invoice(longer, TEMPLATE_IDS[0])
    assert isinstance(b, Image.Image)
    assert ImageChops.difference(a, b).getbbox() is not None


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
@pytest.mark.parametrize("seed", range(100))
def test_generated_text_stays_inside_cells(seed: int, template_id: str) -> None:
    assert find_overflows(generate_invoice(seed), template_id) == []


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_very_long_address_wraps_instead_of_overflowing(invoice: Invoice, template_id: str) -> None:
    long_address = "경상남도 창원시 마산합포구 진동면 진북대로 1234번길 56-78 대한빌딩 3층 301호"
    supplier = invoice.supplier.model_copy(update={"address": long_address})
    long_invoice = invoice.model_copy(update={"supplier": supplier})
    assert find_overflows(long_invoice, template_id) == []
    assert render_invoice(long_invoice, template_id).size == PAGE_SIZE


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
def test_handwriting_differs_from_print(invoice: Invoice, template_id: str) -> None:
    printed = render_invoice(invoice, template_id)
    handwritten = render_invoice(invoice, template_id, handwriting_seed=1)
    assert handwritten.size == PAGE_SIZE
    assert ImageChops.difference(printed, handwritten).getbbox() is not None


def test_handwriting_is_deterministic_per_seed(invoice: Invoice) -> None:
    a = render_invoice(invoice, "classic", handwriting_seed=3)
    b = render_invoice(invoice, "classic", handwriting_seed=3)
    c = render_invoice(invoice, "classic", handwriting_seed=4)
    assert ImageChops.difference(a, b).getbbox() is None
    assert ImageChops.difference(a, c).getbbox() is not None


def test_handwriting_keeps_printed_labels(invoice: Invoice) -> None:
    """라벨(상호, 품목 등)은 인쇄체 그대로이므로 양식의 윗부분 제목 영역은 같다."""
    printed = render_invoice(invoice, "classic")
    handwritten = render_invoice(invoice, "classic", handwriting_seed=1)
    title_area = (0, 0, PAGE_SIZE[0], 190)
    diff = ImageChops.difference(printed.crop(title_area), handwritten.crop(title_area))
    assert diff.getbbox() is None


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
@pytest.mark.parametrize("seed", range(30))
def test_handwritten_text_stays_inside_cells(seed: int, template_id: str) -> None:
    assert find_overflows(generate_invoice(seed), template_id, handwriting_seed=seed) == []


def test_unknown_template_raises(invoice: Invoice) -> None:
    with pytest.raises(ValueError, match="unknown"):
        render_invoice(invoice, "nope")
