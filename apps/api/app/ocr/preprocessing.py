"""OCR 전처리: 디코딩, PDF 분리, 기울기 보정, 대비 개선, 임계화, 리사이즈.

모든 함수는 RGB `NDArray[np.uint8]`(높이 x 너비 x 3)를 받고 같은 형식을 돌려주며,
입력 배열은 바꾸지 않는다. 단계마다 독립 함수라 필요한 것만 골라 이어 붙인다.
어떤 단계를 기본으로 켤지는 이 모듈이 정하지 않는다(호출하는 쪽의 설정이다).
"""

import io
import math
from collections.abc import Iterator
from typing import Protocol, cast

import cv2
import numpy as np
import pypdfium2 as pdfium  # pyright: ignore[reportMissingTypeStubs]
from numpy.typing import NDArray
from PIL import Image, ImageOps

RgbImage = NDArray[np.uint8]


class _PdfBitmap(Protocol):
    def to_pil(self) -> Image.Image: ...


class _PdfPage(Protocol):
    def render(self, scale: float) -> _PdfBitmap: ...


class _PdfDocument(Protocol):
    def __iter__(self) -> "Iterator[_PdfPage]": ...
    def close(self) -> None: ...


def _as_rgb(mat: object) -> RgbImage:
    """cv2가 돌려주는 MatLike를 RGB uint8 배열 타입으로 좁힌다."""
    return np.asarray(mat, dtype=np.uint8)


PDF_BASE_DPI = 72  # PDF 좌표 1pt = 1/72 inch
MIN_DESKEW_ANGLE = 0.3  # 이보다 작은 기울기는 보정하지 않는다(보간 번짐만 생긴다)
MAX_DESKEW_ANGLE = 15.0  # 이보다 큰 기울기는 글줄이 아닌 선으로 보고 무시한다


def decode_image(data: bytes) -> RgbImage:
    """업로드된 이미지 바이트를 RGB 배열로 디코딩한다. EXIF 회전을 반영한다."""
    try:
        with Image.open(io.BytesIO(data)) as source:
            oriented = ImageOps.exif_transpose(source)
            rgb = oriented.convert("RGB")
            return np.asarray(rgb, dtype=np.uint8).copy()
    except (OSError, Image.DecompressionBombError) as error:
        # UnidentifiedImageError는 OSError의 하위 클래스다
        raise ValueError(f"이미지를 디코딩할 수 없다: {error}") from error


def split_pdf(data: bytes, dpi: int = 200) -> list[RgbImage]:
    """PDF를 페이지별 RGB 이미지로 렌더링한다(pypdfium2)."""
    if dpi <= 0:
        raise ValueError(f"dpi는 양수여야 한다: {dpi}")
    try:
        document = cast(_PdfDocument, pdfium.PdfDocument(data))
    except pdfium.PdfiumError as error:  # pyright: ignore[reportUnknownMemberType]
        raise ValueError(f"PDF를 열 수 없다: {error}") from error
    try:
        pages: list[RgbImage] = []
        for page in document:
            rgb = page.render(scale=dpi / PDF_BASE_DPI).to_pil().convert("RGB")
            pages.append(np.asarray(rgb, dtype=np.uint8).copy())
        return pages
    finally:
        document.close()


def estimate_skew_angle(image: RgbImage, max_angle: float = MAX_DESKEW_ANGLE) -> float:
    """글줄의 기울기를 도 단위로 추정한다. 내용이 반시계 방향으로 기울었으면 양수.

    글자를 가로로 뭉쳐 글줄 덩어리로 만든 뒤 확률적 Hough 변환으로 선분을 찾고,
    `max_angle` 이내 선분 각도의 중앙값을 쓴다. 선분을 못 찾으면 0.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    width = image.shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 40, 3), 1))
    lines = cv2.dilate(ink, kernel)
    edges = cv2.Canny(lines, 50, 150)
    found = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 360,
        threshold=100,
        minLineLength=max(width // 4, 20),
        maxLineGap=max(width // 40, 5),
    )
    segments = cast("NDArray[np.int32] | None", found)
    if segments is None:
        return 0.0
    angles: list[float] = []
    for x1, y1, x2, y2 in segments.reshape(-1, 4):
        # 이미지 y축은 아래로 향하므로 부호를 뒤집어 반시계를 양수로 만든다
        angle = -math.degrees(math.atan2(int(y2) - int(y1), int(x2) - int(x1)))
        if abs(angle) <= max_angle:
            angles.append(angle)
    if not angles:
        return 0.0
    return float(np.median(angles))


def deskew(image: RgbImage, max_angle: float = MAX_DESKEW_ANGLE) -> RgbImage:
    """추정한 기울기만큼 되돌려 회전한다. 크기는 유지하고 빈 곳은 흰색으로 채운다.

    기울기가 `MIN_DESKEW_ANGLE`보다 작으면 원본 복사본을 돌려준다.
    큰 각도에서는 모서리가 잘릴 수 있다.
    """
    angle = estimate_skew_angle(image, max_angle)
    if abs(angle) < MIN_DESKEW_ANGLE:
        return image.copy()
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), -angle, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    return _as_rgb(rotated)


def enhance_contrast(image: RgbImage, clip_limit: float = 2.0, tile_size: int = 8) -> RgbImage:
    """LAB 밝기 채널에 CLAHE를 적용한다(색상은 유지)."""
    lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
    lab[..., 0] = clahe.apply(lab[..., 0])
    return _as_rgb(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def adaptive_threshold(image: RgbImage, block_size: int = 31, offset: int = 15) -> RgbImage:
    """가우시안 적응형 임계화로 흑백화한다. 결과는 0/255만 가진 RGB다.

    조명이 고르지 않은 촬영본에 쓰려는 것이다. 깨끗한 이미지에서는 오히려
    획이 얇아질 수 있어 항상 켜는 것이 이득인지는 벤치마크로 판단한다.
    """
    if block_size < 3 or block_size % 2 == 0:
        raise ValueError(f"block_size는 3 이상의 홀수여야 한다: {block_size}")
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    binary = cv2.adaptiveThreshold(
        gray,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        offset,
    )
    return _as_rgb(cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB))


def resize_max_side(image: RgbImage, max_side: int) -> RgbImage:
    """긴 변이 `max_side`를 넘으면 비율을 유지해 줄인다. 작은 이미지는 확대하지 않는다."""
    if max_side <= 0:
        raise ValueError(f"max_side는 양수여야 한다: {max_side}")
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_side:
        return image.copy()
    ratio = max_side / longest
    new_size = (max(round(width * ratio), 1), max(round(height * ratio), 1))
    return _as_rgb(cv2.resize(image, new_size, interpolation=cv2.INTER_AREA))
