"""이미지 전처리 단위 테스트. 모델 로딩 없이 합성 이미지로 검증한다."""

import io
from pathlib import Path

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from app.ocr.preprocessing import (
    adaptive_threshold,
    decode_image,
    deskew,
    enhance_contrast,
    estimate_skew_angle,
    resize_max_side,
    split_pdf,
)

Image3 = NDArray[np.uint8]


def make_text_lines(width: int = 800, height: int = 600) -> Image3:
    """가로 글줄 모양(두꺼운 선 여러 개)이 있는 흰 배경 이미지."""
    image = np.full((height, width, 3), 255, dtype=np.uint8)
    for row in range(8):
        y = 80 + row * 55
        for col in range(10):
            x = 60 + col * 70
            cv2.putText(image, "Ab12", (x, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return image


def rotate(image: Image3, angle: float) -> Image3:
    """반시계 방향 angle도 회전(빈 곳은 흰색). 테스트용 기준 구현."""
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    rotated = cv2.warpAffine(image, matrix, (width, height), borderValue=(255, 255, 255))
    return np.asarray(rotated, dtype=np.uint8)


def assert_rgb_uint8(image: Image3) -> None:
    assert image.dtype == np.uint8
    assert image.ndim == 3
    assert image.shape[2] == 3


class TestSkew:
    @pytest.mark.parametrize("angle", [-8.0, -3.0, 2.0, 5.0, 10.0])
    def test_추정_각도가_실제와_가깝다(self, angle: float) -> None:
        skewed = rotate(make_text_lines(), angle)
        assert estimate_skew_angle(skewed) == pytest.approx(angle, abs=0.7)

    def test_기울지_않은_이미지는_0에_가깝다(self) -> None:
        assert estimate_skew_angle(make_text_lines()) == pytest.approx(0.0, abs=0.5)

    def test_글자가_없는_빈_이미지는_0을_돌려준다(self) -> None:
        blank = np.full((300, 300, 3), 255, dtype=np.uint8)
        assert estimate_skew_angle(blank) == 0.0

    def test_deskew는_기울기를_펴고_크기를_유지한다(self) -> None:
        skewed = rotate(make_text_lines(), 6.0)
        fixed = deskew(skewed)
        assert_rgb_uint8(fixed)
        assert fixed.shape == skewed.shape
        assert abs(estimate_skew_angle(fixed)) < 0.7

    def test_deskew는_작은_각도는_원본을_그대로_돌려준다(self) -> None:
        image = make_text_lines()
        assert np.array_equal(deskew(image), image)

    def test_deskew는_입력을_변경하지_않는다(self) -> None:
        skewed = rotate(make_text_lines(), 6.0)
        before = skewed.copy()
        deskew(skewed)
        assert np.array_equal(skewed, before)


class TestContrast:
    def test_저대비_이미지의_대비가_커진다(self) -> None:
        rng = np.random.default_rng(0)
        low = rng.integers(110, 140, size=(200, 200, 3), dtype=np.uint8)
        result = enhance_contrast(low)
        assert_rgb_uint8(result)
        assert result.shape == low.shape
        assert result.std() > low.std()


class TestThreshold:
    def test_결과는_흑백_값만_가진_RGB다(self) -> None:
        result = adaptive_threshold(make_text_lines())
        assert_rgb_uint8(result)
        assert set(np.unique(result)) <= {0, 255}
        assert (result[..., 0] == result[..., 1]).all()

    def test_불균일한_조명에서도_글자가_남는다(self) -> None:
        image = make_text_lines()
        gradient = np.linspace(1.0, 0.45, image.shape[1], dtype=np.float32)
        shaded = (image.astype(np.float32) * gradient[None, :, None]).astype(np.uint8)
        result = adaptive_threshold(shaded)
        # 왼쪽 끝과 오른쪽 끝 모두에서 글자(검정)가 같은 정도로 검출돼야 한다
        left = (result[:, :200] == 0).mean()
        right = (result[:, -200:] == 0).mean()
        assert left > 0.01
        assert right > 0.01
        assert right / left == pytest.approx(1.0, abs=0.5)


class TestResize:
    def test_긴_변이_상한을_넘으면_비율을_유지해_줄인다(self) -> None:
        image = np.zeros((1000, 2000, 3), dtype=np.uint8)
        result = resize_max_side(image, 1000)
        assert_rgb_uint8(result)
        assert result.shape == (500, 1000, 3)

    def test_세로가_긴_이미지도_긴_변_기준이다(self) -> None:
        image = np.zeros((3000, 1000, 3), dtype=np.uint8)
        assert resize_max_side(image, 1500).shape == (1500, 500, 3)

    def test_상한_이하면_확대하지_않고_그대로다(self) -> None:
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        assert resize_max_side(image, 1000).shape == (100, 200, 3)

    def test_상한이_0_이하면_ValueError(self) -> None:
        with pytest.raises(ValueError):
            resize_max_side(np.zeros((10, 10, 3), dtype=np.uint8), 0)


class TestDecode:
    def test_PNG_바이트를_RGB로_디코딩한다(self) -> None:
        source = np.zeros((20, 30, 3), dtype=np.uint8)
        source[..., 0] = 200  # R
        buffer = io.BytesIO()
        Image.fromarray(source).save(buffer, format="PNG")
        result = decode_image(buffer.getvalue())
        assert_rgb_uint8(result)
        assert result.shape == (20, 30, 3)
        assert result[0, 0].tolist() == [200, 0, 0]

    def test_RGBA와_그레이스케일도_RGB로_바꾼다(self) -> None:
        for mode in ("RGBA", "L"):
            buffer = io.BytesIO()
            Image.new(mode, (10, 10)).save(buffer, format="PNG")
            assert_rgb_uint8(decode_image(buffer.getvalue()))

    def test_EXIF_회전을_반영한다(self) -> None:
        image = Image.new("RGB", (40, 20), (255, 255, 255))
        exif = Image.Exif()
        exif[0x0112] = 6  # 시계 방향 90도 회전해서 봐야 한다
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", exif=exif)
        assert decode_image(buffer.getvalue()).shape[:2] == (40, 20)

    def test_이미지가_아니면_ValueError(self) -> None:
        with pytest.raises(ValueError):
            decode_image(b"not an image")


def make_pdf(page_count: int) -> bytes:
    """Pillow로 300x400pt 페이지 여러 장짜리 PDF를 만든다(72dpi 기준 픽셀=pt)."""
    pages = [Image.new("RGB", (300, 400), (255, 255, 255)) for _ in range(page_count)]
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:], resolution=72)
    return buffer.getvalue()


class TestSplitPdf:
    def test_페이지마다_RGB_이미지를_돌려준다(self) -> None:
        pages = split_pdf(make_pdf(3), dpi=72)
        assert len(pages) == 3
        for page in pages:
            assert_rgb_uint8(page)
            assert page.shape == (400, 300, 3)

    def test_dpi에_비례해_커진다(self) -> None:
        small = split_pdf(make_pdf(1), dpi=72)[0]
        large = split_pdf(make_pdf(1), dpi=144)[0]
        assert large.shape[0] == small.shape[0] * 2

    def test_PDF가_아니면_ValueError(self) -> None:
        with pytest.raises(ValueError):
            split_pdf(b"not a pdf")


GOLDEN_DIR = Path(__file__).resolve().parents[4] / "samples" / "golden"


def load_golden(name: str) -> Image3:
    return decode_image((GOLDEN_DIR / name).read_bytes())


class TestGoldenSet:
    """골든셋 변형별로 전처리가 이미지를 망가뜨리지 않는지 확인한다(모델 불필요)."""

    @pytest.mark.parametrize("difficulty", ["clean", "skewed", "low_res", "photo"])
    def test_전체_단계를_거쳐도_형식이_유지된다(self, difficulty: str) -> None:
        import json

        label = next(
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(GOLDEN_DIR.glob("invoice_*.json"))
            if json.loads(p.read_text(encoding="utf-8"))["difficulty"] == difficulty
        )
        image = load_golden(label["image"])
        result = resize_max_side(enhance_contrast(deskew(image)), 2000)
        assert_rgb_uint8(result)
        assert max(result.shape[:2]) <= 2000

    def test_기울어진_골든셋은_보정_후_기울기가_줄어든다(self) -> None:
        import json

        before: list[float] = []
        after: list[float] = []
        for path in sorted(GOLDEN_DIR.glob("invoice_*.json")):
            label = json.loads(path.read_text(encoding="utf-8"))
            if label["difficulty"] != "skewed":
                continue
            image = load_golden(label["image"])
            before.append(abs(estimate_skew_angle(image)))
            after.append(abs(estimate_skew_angle(deskew(image))))
        assert before
        assert sum(after) < sum(before)
