"""Strands ツール: フェーズ1 の検索API(CriminalLawKB)をエージェントへ公開する。

KB のロード（schema+data 統合 + owlrl 推論）は高コストのため、
プロセス内で一度だけ構築してキャッシュする。
"""

from __future__ import annotations

from functools import lru_cache

from criminal_ontology.query import CriminalLawKB
from strands import tool


@lru_cache(maxsize=1)
def get_kb() -> CriminalLawKB:
    """刑法オントロジー KB をロード（初回のみ推論適用）。"""
    return CriminalLawKB.load()


@tool
def resolve_concepts(consultation: str) -> list[dict]:
    """相談文をセマンティックレイヤーで法律概念へ正規化する（表現ゆらぎを吸収）。

    Args:
        consultation: 利用者の相談文（日常語）。

    Returns:
        マッチした概念のリスト。各要素は concept_id / pref_label /
        matched_surface / indicates_crimes / score を含む。
    """
    return get_kb().resolve_concepts(consultation)


@tool
def search_crimes_by_text(consultation: str) -> list[dict]:
    """相談文 → 概念 → 罪候補を解決して返す（概念経由の2段階検索）。

    該当しうる罪が無い場合は空リストを返す（刑法上該当なしの可能性）。

    Args:
        consultation: 利用者の相談文（日常語）。

    Returns:
        罪候補のリスト。各要素は crime_id / label / article / category /
        penalties / score / via_concepts を含む。スコア降順。
    """
    cands = get_kb().search_by_text(consultation)
    return [
        {
            "crime_id": c.crime_id,
            "label": c.label,
            "article": c.article,
            "category": c.category,
            "penalties": c.penalties,
            "score": round(c.score, 2),
            "via_concepts": c.via_concepts,
        }
        for c in cands
    ]


@tool
def get_crime_detail(crime_id: str) -> dict:
    """罪 ID から条文・構成要件・法定刑の詳細を取得する。

    Args:
        crime_id: 罪の識別子（例: "theft", "assault"）。

    Returns:
        罪詳細の辞書。存在しない場合は {"error": ...}。
    """
    d = get_kb().get_crime(crime_id)
    if d is None:
        return {"error": f"unknown crime_id: {crime_id}"}
    return {
        "crime_id": d.crime_id,
        "label": d.label,
        "article": d.article,
        "category": d.category,
        "legal_interest": d.legal_interest,
        "statute_text": d.statute_text,
        "elements": d.elements,
        "penalties": d.penalties,
        "related_to": d.related_to,
    }


@tool
def list_crime_categories() -> list[dict]:
    """収録している罪のカテゴリ一覧（保護法益の分類）を返す。

    Returns:
        カテゴリのリスト。各要素は id / label / count / direct_count / leaf。
    """
    return get_kb().list_categories()
