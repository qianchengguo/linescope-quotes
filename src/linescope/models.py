"""Small contracts shared by the API, local model and deterministic verifier."""

import re
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Page(Contract):
    number: int = Field(ge=1, le=8)
    text: str = Field(min_length=1, max_length=12000)


class Document(Contract):
    pages: list[Page] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def bounded_unique_pages(self):
        if len({p.number for p in self.pages}) != len(self.pages):
            raise ValueError("page numbers must be unique")
        if sum(len(p.text) for p in self.pages) > 24000:
            raise ValueError("maximum 24000 source characters")
        return self


class Evidence(Contract):
    page: int = Field(ge=1, le=8)
    quote: str = Field(min_length=1, max_length=2000)


class NumberField(Contract):
    value: Decimal | None
    evidence: Evidence | None

    @field_validator("value", mode="before")
    @classmethod
    def decimal_strings_only(cls, value):
        # JSON numbers could already have lost precision before reaching us.
        if value is not None and (
            not isinstance(value, str)
            or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,4})?", value)
        ):
            raise ValueError("use a non-negative decimal string, <=9 integer/4 decimal digits")
        return value


class TextField(Contract):
    value: str | None = Field(max_length=200)
    evidence: Evidence | None


class Item(Contract):
    item_id: str = Field(min_length=1, max_length=40)
    scope: Evidence | None
    name: TextField
    quantity: NumberField
    unit_price: NumberField
    amount: NumberField


class Extraction(Contract):
    currency: TextField
    items: list[Item] = Field(min_length=1, max_length=20)
    total: NumberField
    notes: list[str] = Field(max_length=10)

    @field_validator("notes")
    @classmethod
    def bounded_notes(cls, notes):
        if any(len(note) > 500 for note in notes):
            raise ValueError("each note must be <=500 characters")
        return notes

    @model_validator(mode="after")
    def unique_ids(self):
        if len({i.item_id for i in self.items}) != len(self.items):
            raise ValueError("item IDs must be unique")
        return self


class Review(Contract):
    coverage_confirmed: bool = False
    simple_pricing_confirmed: bool = False
    reviewer: str = Field(default="", max_length=80)
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def require_review_note(self):
        if (self.coverage_confirmed or self.simple_pricing_confirmed) and (
            not self.reviewer.strip() or not self.reason.strip()
        ):
            raise ValueError("confirmations require reviewer label and reason")
        return self


class Finding(Contract):
    code: str
    severity: Literal["blocked", "review"]
    path: str
    message: str


class CheckReport(Contract):
    verifier_version: str = "0.1.0"
    document_sha256: str
    verdict: Literal["BLOCKED", "NEEDS_REVIEW", "CHECKS_PASSED"]
    findings: list[Finding]
    anchors: dict[str, dict[str, int]]
    calculations: list[dict[str, str]]
