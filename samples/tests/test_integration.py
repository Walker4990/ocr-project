"""생성기 데이터가 모든 양식에 들어가는지 확인한다."""
import pytest
from doculens_samples.data import generate_invoice
from doculens_samples.render import PAGE_SIZE, TEMPLATE_IDS, render_invoice


@pytest.mark.parametrize("template_id", TEMPLATE_IDS)
@pytest.mark.parametrize("seed", range(40))
def test_generated_invoice_renders_on_every_template(seed: int, template_id: str) -> None:
    image = render_invoice(generate_invoice(seed), template_id)
    assert image.size == PAGE_SIZE
