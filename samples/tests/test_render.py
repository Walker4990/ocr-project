"""거래명세서 템플릿 렌더링 테스트."""
import numpy as np
import pytest
from doculens_samples.render import PAGE_SIZE, TEMPLATE_IDS, render_invoice
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


def test_unknown_template_raises(invoice: Invoice) -> None:
    with pytest.raises(ValueError, match="unknown"):
        render_invoice(invoice, "nope")
