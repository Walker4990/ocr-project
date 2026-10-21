"""난이도별 이미지 변형 테스트."""
import numpy as np
import pytest
from doculens_samples.degrade import DIFFICULTIES, degrade
from doculens_samples.render import render_invoice
from doculens_samples.schema import Invoice
from PIL import Image, ImageChops


@pytest.fixture
def page(invoice: Invoice) -> Image.Image:
    return render_invoice(invoice, "classic")


def _differs(a: Image.Image, b: Image.Image) -> bool:
    return a.size != b.size or ImageChops.difference(a, b).getbbox() is not None


def test_difficulty_names() -> None:
    assert set(DIFFICULTIES) == {"clean", "skewed", "low_res", "photo"}


def test_clean_keeps_image_unchanged(page: Image.Image) -> None:
    assert not _differs(degrade(page, "clean", seed=1), page)


def test_skewed_keeps_size_but_changes_pixels(page: Image.Image) -> None:
    result = degrade(page, "skewed", seed=1)
    assert result.size == page.size
    assert _differs(result, page)


def test_low_res_is_smaller(page: Image.Image) -> None:
    result = degrade(page, "low_res", seed=1)
    assert result.width < page.width * 0.6
    assert result.height < page.height * 0.6


def test_photo_is_darker_and_noisy(page: Image.Image) -> None:
    result = degrade(page, "photo", seed=1)
    assert result.mode == "RGB"
    assert _differs(result, page)
    assert np.asarray(result).mean() < np.asarray(page).mean()


@pytest.mark.parametrize("difficulty", DIFFICULTIES)
def test_degrade_is_deterministic(page: Image.Image, difficulty: str) -> None:
    assert not _differs(degrade(page, difficulty, seed=3), degrade(page, difficulty, seed=3))


@pytest.mark.parametrize("difficulty", ["skewed", "photo"])
def test_different_seeds_give_different_results(page: Image.Image, difficulty: str) -> None:
    assert _differs(degrade(page, difficulty, seed=1), degrade(page, difficulty, seed=2))


def test_unknown_difficulty_raises(page: Image.Image) -> None:
    with pytest.raises(ValueError, match="unknown"):
        degrade(page, "blurry", seed=1)
