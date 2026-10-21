"""이미지 한 장에 대응하는 정답 라벨(JSON)."""
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from doculens_samples.degrade import Difficulty
from doculens_samples.schema import Invoice

Writing = Literal["print", "handwritten"]


class GoldenLabel(BaseModel):
    model_config = ConfigDict(frozen=True)

    image: str
    template_id: str
    difficulty: Difficulty
    # 손글씨는 폰트로 흉내 낸 모사 데이터다. 이전 라벨에는 필드가 없어 기본값은 인쇄체다
    writing: Writing = "print"
    seed: int
    invoice: Invoice


def write_label(label: GoldenLabel, path: Path) -> None:
    path.write_text(label.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def read_label(path: Path) -> GoldenLabel:
    return GoldenLabel.model_validate_json(path.read_text(encoding="utf-8"))
