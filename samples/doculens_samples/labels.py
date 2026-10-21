"""이미지 한 장에 대응하는 정답 라벨(JSON)."""
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from doculens_samples.degrade import Difficulty
from doculens_samples.schema import Invoice


class GoldenLabel(BaseModel):
    model_config = ConfigDict(frozen=True)

    image: str
    template_id: str
    difficulty: Difficulty
    seed: int
    invoice: Invoice


def write_label(label: GoldenLabel, path: Path) -> None:
    path.write_text(label.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def read_label(path: Path) -> GoldenLabel:
    return GoldenLabel.model_validate_json(path.read_text(encoding="utf-8"))
