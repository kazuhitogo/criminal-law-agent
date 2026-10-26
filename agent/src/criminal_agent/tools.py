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


# 0 件時の差し戻し（SPEC §5.2）。言い換え自体は文脈理解が要るので LLM に任せ、
# 方針だけをツール結果で渡す。
RESUBMIT = {
    "reason": "辞書に一致する語が無く、罪候補が 0 件だった。相談文を言い換えて再検索すること。",
    "strategies": [
        {
            "name": "被害者視点の受け身形",
            "example": "盗んだ → 盗まれた、殴った → 殴られた",
        },
        {
            "name": "俗語を標準語へ",
            "example": "パクった → 盗まれた、ボコられた → 殴られた（受け身形と組み合わせる）",
        },
        {
            "name": "法律用語・罪名",
            "example": "窃盗、横領、暴行（罪名から「罪」を除いた語。窃取などの条文の用語は辞書に無いことが多い）",
        },
    ],
    "constraints": [
        "辞書の語は被害者視点の受け身形が中心。①②を先に試す",
        "表現（視点・語彙）だけを変え、事実を足さない・変えない",
        "1 つの事実につき言い換えは 2 回まで。2 回とも 0 件なら候補なしとする",
    ],
}


@tool
def search_crimes_by_text(consultation: str) -> dict:
    """相談文 → 概念 → 罪候補を解決して返す（概念経由の2段階検索）。

    候補が 0 件のときは resubmit（言い換えの方針）を返す。その方針で言い換えて再検索する。

    Args:
        consultation: 利用者の相談文（日常語）。言い換え後の文でもよい。

    Returns:
        {"query", "candidates", "resubmit"}。
        candidates の各要素は crime_id / label / article / category /
        penalties / score / via_concepts / matched_surface を含む。スコア降順。
        matched_surface は query 中で辞書にマッチした語（判断根拠）。
        resubmit は 0 件のときだけ値を持ち、ヒット時は null。
    """
    cands = get_kb().search_by_text(consultation)
    candidates = [
        {
            "crime_id": c.crime_id,
            "label": c.label,
            "article": c.article,
            "category": c.category,
            "penalties": c.penalties,
            "score": round(c.score, 2),
            "via_concepts": c.via_concepts,
            "matched_surface": c.matched_surface,
        }
        for c in cands
    ]
    return {
        "query": consultation,
        "candidates": candidates,
        "resubmit": None if candidates else RESUBMIT,
    }


@tool
def get_crime_detail(crime_id: str) -> dict:
    """罪 ID から条文・構成要件・法定刑の詳細を取得する。

    Args:
        crime_id: 罪の識別子（例: "theft", "assault"）。

    Returns:
        罪詳細の辞書。存在しない場合は {"error": ...}。
        related_to の各要素は crime_id / label / article（オントロジーの値）。
    """
    kb = get_kb()
    d = kb.get_crime(crime_id)
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
        "related_to": [_related_ref(kb, rid) for rid in d.related_to],
    }


def _related_ref(kb: CriminalLawKB, crime_id: str) -> dict:
    """関連罪 ID に罪名・条番号を付ける（LLM に記憶で補わせないため）。

    引けない ID は落とさず、id だけで返す。
    """
    r = kb.get_crime(crime_id)
    if r is None:
        return {"crime_id": crime_id}
    return {"crime_id": crime_id, "label": r.label, "article": r.article}


@tool
def list_crime_categories() -> list[dict]:
    """収録している罪のカテゴリ一覧（保護法益の分類）を返す。

    Returns:
        カテゴリのリスト。各要素は id / label / count / direct_count / leaf。
    """
    return get_kb().list_categories()
