"""골든셋 배치 생성과 검증 테스트."""
from pathlib import Path

import pytest
from doculens_samples.batch import generate_golden, validate_golden
from doculens_samples.degrade import DIFFICULTIES
from doculens_samples.labels import read_label
from doculens_samples.render import TEMPLATE_IDS

COUNT = 20


@pytest.fixture(scope="module")
def golden_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("golden")
    generate_golden(out, count=COUNT, seed=0)
    return out


def _images(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix in {".png", ".jpg"})


def test_image_and_label_counts_match(golden_dir: Path) -> None:
    images = [p.stem for p in _images(golden_dir)]
    labels = sorted(p.stem for p in golden_dir.glob("*.json"))
    assert len(images) == COUNT
    assert images == labels


def test_each_image_is_small_enough_to_commit(golden_dir: Path) -> None:
    for image in _images(golden_dir):
        assert image.stat().st_size < 1_000_000, image.name


def test_covers_every_template_and_difficulty(golden_dir: Path) -> None:
    labels = [read_label(p) for p in golden_dir.glob("*.json")]
    assert {label.template_id for label in labels} == set(TEMPLATE_IDS)
    assert {label.difficulty for label in labels} == set(DIFFICULTIES)


def test_label_points_to_its_image(golden_dir: Path) -> None:
    images = {p.name for p in _images(golden_dir)}
    for path in golden_dir.glob("*.json"):
        assert read_label(path).image in images
        assert Path(read_label(path).image).stem == path.stem


def test_generated_set_is_valid(golden_dir: Path) -> None:
    assert validate_golden(golden_dir) == []


def test_generation_is_reproducible(golden_dir: Path, tmp_path: Path) -> None:
    generate_golden(tmp_path, count=COUNT, seed=0)
    for original in golden_dir.iterdir():
        assert (tmp_path / original.name).read_bytes() == original.read_bytes()


def test_validate_reports_missing_label(golden_dir: Path, tmp_path: Path) -> None:
    generate_golden(tmp_path, count=5, seed=0)
    next(tmp_path.glob("*.json")).unlink()
    problems = validate_golden(tmp_path)
    assert len(problems) == 1
    assert "라벨 없음" in problems[0]


def test_validate_reports_broken_label(tmp_path: Path) -> None:
    generate_golden(tmp_path, count=5, seed=0)
    next(tmp_path.glob("*.json")).write_text("{}", encoding="utf-8")
    assert any("라벨 파싱 실패" in p for p in validate_golden(tmp_path))
