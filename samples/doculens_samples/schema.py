"""거래명세서 데이터 모델. 렌더링 입력이자 정답 라벨의 원본이다."""
from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


class Party(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    business_number: str
    representative: str
    address: str


class LineItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    spec: str
    quantity: int
    unit_price: int
    amount: int


class Invoice(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_no: str
    issue_date: date
    supplier: Party
    buyer: Party
    items: list[LineItem]
    supply_amount: int
    tax_amount: int
    total_amount: int

    @model_validator(mode="after")
    def _check_amounts(self) -> Self:
        for item in self.items:
            if item.amount != item.quantity * item.unit_price:
                raise ValueError(f"item amount mismatch: {item.name}")
        if self.supply_amount != sum(item.amount for item in self.items):
            raise ValueError("supply amount does not match the sum of items")
        if self.total_amount != self.supply_amount + self.tax_amount:
            raise ValueError("total amount does not match supply + tax")
        return self
