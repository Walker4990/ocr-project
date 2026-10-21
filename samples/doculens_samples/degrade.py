"""깨끗한 렌더링 결과를 난이도별로 열화시킨다. 같은 (이미지, 난이도, seed)면 결과가 같다."""
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

Difficulty = Literal["clean", "skewed", "low_res", "photo"]
DIFFICULTIES: tuple[Difficulty, ...] = ("clean", "skewed", "low_res", "photo")

DESK_COLOR = (92, 84, 76)
LOW_RES_SCALE = 0.38


def _skew(image: Image.Image, rng: np.random.Generator) -> Image.Image:
    angle = float(rng.uniform(1.5, 4.0)) * (1 if rng.random() < 0.5 else -1)
    return image.rotate(
        angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(255, 255, 255)
    )


def _add_noise(image: Image.Image, rng: np.random.Generator, sigma: float) -> Image.Image:
    pixels = np.asarray(image, dtype=np.float32)
    noisy = pixels + rng.normal(0.0, sigma, pixels.shape).astype(np.float32)
    return Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8), mode="RGB")


def _low_res(image: Image.Image, rng: np.random.Generator) -> Image.Image:
    size = (round(image.width * LOW_RES_SCALE), round(image.height * LOW_RES_SCALE))
    small = image.resize(size, Image.Resampling.BILINEAR)
    return _add_noise(small, rng, sigma=3.0)


def _perspective_coefficients(
    output_corners: list[tuple[float, float]], source_corners: list[tuple[float, float]]
) -> list[float]:
    """출력 좌표 -> 원본 좌표로 가는 PIL 원근 변환 계수 8개를 구한다."""
    rows: list[list[float]] = []
    targets: list[float] = []
    for (x, y), (sx, sy) in zip(output_corners, source_corners, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -sx * x, -sx * y])
        rows.append([0, 0, 0, x, y, 1, -sy * x, -sy * y])
        targets += [sx, sy]
    solved: NDArray[np.float64] = np.linalg.solve(np.array(rows), np.array(targets))
    return [float(v) for v in solved]


def _shadow_mask(width: int, height: int, rng: np.random.Generator) -> NDArray[np.float32]:
    """한쪽이 어두운 조명 그라데이션 (0.6~1.0)."""
    theta = float(rng.uniform(0, 2 * np.pi))
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    ramp = (xs / width - 0.5) * np.cos(theta) + (ys / height - 0.5) * np.sin(theta)
    strength = float(rng.uniform(0.25, 0.4))
    return np.clip(1.0 - strength * (ramp + 0.5), 0.0, 1.0).astype(np.float32)


def _photo(image: Image.Image, rng: np.random.Generator) -> Image.Image:
    width, height = image.size
    desk = Image.new("RGB", image.size, DESK_COLOR)
    inset = 0.88
    page = image.resize((round(width * inset), round(height * inset)), Image.Resampling.LANCZOS)
    desk.paste(page, ((width - page.width) // 2, (height - page.height) // 2))

    jitter = 0.03
    corners = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    source = [
        (x + float(rng.uniform(-jitter, jitter)) * width,
         y + float(rng.uniform(-jitter, jitter)) * height)
        for x, y in corners
    ]
    coefficients = _perspective_coefficients(corners, source)
    warped = desk.transform(
        image.size,
        Image.Transform.PERSPECTIVE,
        coefficients,
        resample=Image.Resampling.BICUBIC,
        fillcolor=DESK_COLOR,
    )

    lit = np.asarray(warped, dtype=np.float32) * _shadow_mask(width, height, rng)[..., None]
    shaded = Image.fromarray(np.clip(lit * 0.95, 0, 255).astype(np.uint8), mode="RGB")
    blurred = shaded.filter(ImageFilter.GaussianBlur(radius=float(rng.uniform(0.6, 1.2))))
    return _add_noise(blurred, rng, sigma=6.0)


def degrade(image: Image.Image, difficulty: str, seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    if difficulty == "clean":
        return image.copy()
    if difficulty == "skewed":
        return _skew(image, rng)
    if difficulty == "low_res":
        return _low_res(image, rng)
    if difficulty == "photo":
        return _photo(image, rng)
    raise ValueError(f"unknown difficulty: {difficulty}")
