"""골든셋 배치 생성과 검증. 양식 x 난이도 조합을 번갈아 순회해 모든 조합을 고르게 채운다."""
from pathlib import Path

from pydantic import ValidationError

from doculens_samples.data import generate_invoice
from doculens_samples.degrade import DIFFICULTIES, degrade
from doculens_samples.labels import GoldenLabel, read_label, write_label
from doculens_samples.render import TEMPLATE_IDS, render_invoice

IMAGE_SUFFIXES = {".png", ".jpg"}
# 노이즈가 들어가는 난이도는 PNG로 저장하면 장당 수 MB가 되므로 실제 촬영본처럼 JPEG로 저장한다
JPEG_DIFFICULTIES = {"low_res", "photo"}
JPEG_QUALITY = 85


def _image_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix in IMAGE_SUFFIXES)


def generate_golden(out_dir: Path, count: int, seed: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        item_seed = seed * 100_000 + index
        template_id = TEMPLATE_IDS[index % len(TEMPLATE_IDS)]
        difficulty = DIFFICULTIES[(index // len(TEMPLATE_IDS)) % len(DIFFICULTIES)]
        invoice = generate_invoice(item_seed)

        stem = f"invoice_{index:03d}"
        image = degrade(render_invoice(invoice, template_id), difficulty, item_seed)
        if difficulty in JPEG_DIFFICULTIES:
            file_name = f"{stem}.jpg"
            image.save(out_dir / file_name, quality=JPEG_QUALITY)
        else:
            file_name = f"{stem}.png"
            image.save(out_dir / file_name, optimize=True)
        label = GoldenLabel(
            image=file_name,
            template_id=template_id,
            difficulty=difficulty,
            seed=item_seed,
            invoice=invoice,
        )
        write_label(label, out_dir / f"{stem}.json")


def validate_golden(directory: Path) -> list[str]:
    """이미지-라벨 짝과 라벨 스키마를 점검하고 문제 목록을 돌려준다(비어 있으면 정상)."""
    problems: list[str] = []
    images = {p.stem: p.name for p in _image_files(directory)}
    labels = {p.stem for p in directory.glob("*.json")}
    problems += [f"{stem}: 라벨 없음" for stem in sorted(images.keys() - labels)]
    problems += [f"{stem}: 이미지 없음" for stem in sorted(labels - images.keys())]
    for stem in sorted(images.keys() & labels):
        try:
            label = read_label(directory / f"{stem}.json")
        except ValidationError as error:
            problems.append(f"{stem}: 라벨 파싱 실패 ({error.error_count()}건)")
            continue
        if label.image != images[stem]:
            problems.append(f"{stem}: 라벨의 image 필드가 {label.image}를 가리킴")
    return problems
