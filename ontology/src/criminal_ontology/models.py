"""刑法オントロジーの pydantic データモデル。

YAML ソース（crimes.yaml / semantics.yaml）をバリデーションし、
ビルダ・検索APIが扱う型付きオブジェクトへ変換する。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ElementType(str, Enum):
    """構成要件要素の種別。"""

    conduct = "conduct"        # 行為
    result = "result"          # 結果
    object = "object"          # 客体
    circumstance = "circumstance"  # 状況・付随事情
    intent = "intent"          # 故意・目的・過失


# 要素種別 → schema.ttl のクラス名
ELEMENT_CLASS_MAP: dict[str, str] = {
    "conduct": "ConductElement",
    "result": "ResultElement",
    "object": "ObjectElement",
    "circumstance": "CircumstanceElement",
    "intent": "IntentElement",
}


class PenaltyType(str, Enum):
    """刑種。"""

    death = "death"              # 死刑
    imprisonment = "imprisonment"  # 拘禁刑
    fine = "fine"                # 罰金・科料


# 刑種 → schema.ttl のクラス名
PENALTY_CLASS_MAP: dict[str, str] = {
    "death": "DeathPenalty",
    "imprisonment": "Imprisonment",
    "fine": "Fine",
}


class PenaltyUnit(str, Enum):
    """法定刑の単位。"""

    month = "month"
    year = "year"
    yen = "yen"


# 罪カテゴリ（schema.ttl のクラス名と一致させる）
VALID_CATEGORIES: set[str] = {
    "CrimeAgainstLifeBody",
    "CrimeAgainstFreedomHonor",
    "CrimeAgainstProperty",
    "CrimeAgainstPublicSafety",
    "CrimeAgainstPublicTrust",
    "CrimeAgainstPublicMorals",
    "CrimeAgainstStateExistence",
    "CrimeAgainstStateFunction",
}


class Element(BaseModel):
    """構成要件要素。"""

    type: ElementType
    desc: str
    keywords: list[str] = Field(default_factory=list)


class Penalty(BaseModel):
    """法定刑。"""

    type: PenaltyType
    min: int | None = None
    max: int | None = None
    unit: PenaltyUnit | None = None
    note: str

    @field_validator("unit", mode="before")
    @classmethod
    def _empty_unit_to_none(cls, v: object) -> object:
        if v in ("", None):
            return None
        return v


class Crime(BaseModel):
    """罪（1罪 = crimes.yaml の1エントリ）。"""

    id: str
    label: str
    article: str
    category: str
    legal_interest: str
    elements: list[Element] = Field(default_factory=list)
    penalties: list[Penalty] = Field(default_factory=list)
    statute_text: str
    related_to: list[str] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def _valid_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(
                f"unknown category: {v!r}. valid: {sorted(VALID_CATEGORIES)}"
            )
        return v


class Article(BaseModel):
    """条文。crimes.yaml から派生生成する。"""

    number: str
    statute_text: str


class Concept(BaseModel):
    """セマンティックレイヤーの概念（SKOS Concept）。"""

    id: str
    pref_label: str
    alt_labels: list[str] = Field(default_factory=list)
    broader: str | None = None
    indicates_crimes: list[str] = Field(default_factory=list)


class CrimesFile(BaseModel):
    """crimes.yaml のトップレベル構造。"""

    crimes: list[Crime]


class SemanticsFile(BaseModel):
    """semantics.yaml のトップレベル構造。"""

    concepts: list[Concept]
