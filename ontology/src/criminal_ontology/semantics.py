"""セマンティックレイヤー。

相談文(日常語)を SKOS 概念へ正規化し、概念 → 罪候補へ橋渡しする。
概念データは semantics.yaml をロードして保持する（検索はインメモリ）。
RDF グラフ側(build/semantics.ttl)は推論・SPARQL 用途で別途ビルドする。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import Concept, SemanticsFile


@dataclass
class ConceptMatch:
    """相談文にマッチした概念と、その根拠・スコア。"""

    concept_id: str
    pref_label: str
    matched_surface: list[str] = field(default_factory=list)
    indicates_crimes: list[str] = field(default_factory=list)
    score: float = 0.0


class SemanticLayer:
    """概念辞書を保持し、相談文から概念を解決する。"""

    def __init__(self, concepts: list[Concept]):
        self._concepts: dict[str, Concept] = {c.id: c for c in concepts}
        # 表層語(正規化済み) → concept_id のインデックス
        self._surface_index: dict[str, list[str]] = {}
        for c in concepts:
            surfaces = [c.pref_label, *c.alt_labels]
            for s in surfaces:
                key = self._normalize(s)
                if not key:
                    continue
                self._surface_index.setdefault(key, []).append(c.id)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SemanticLayer":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        parsed = SemanticsFile(**data)
        return cls(parsed.concepts)

    _REMOVE_RE = re.compile(r"[\s、。,.!?！？「」『』()（）]")

    @classmethod
    def _normalize(cls, text: str) -> str:
        """比較用の正規化。空白・記号を除去し小文字化。"""
        return cls._normalize_with_map(text)[0]

    @classmethod
    def _normalize_with_map(cls, text: str) -> tuple[str, list[int]]:
        """正規化文字列と、正規化後の各文字 → 原文インデックスの対応表を返す。

        1 文字ずつ小文字化・除去判定するため、lower() で文字数が変わる場合も
        対応表は正しく保たれる。
        """
        out: list[str] = []
        index_map: list[int] = []
        for i, ch in enumerate(text):
            if cls._REMOVE_RE.fullmatch(ch):
                continue
            for lc in ch.lower():
                if cls._REMOVE_RE.fullmatch(lc):
                    continue
                out.append(lc)
                index_map.append(i)
        return "".join(out), index_map

    def get_concept(self, concept_id: str) -> Concept | None:
        return self._concepts.get(concept_id)

    def all_concepts(self) -> list[Concept]:
        return list(self._concepts.values())

    def broader_closure(self, concept_id: str) -> list[str]:
        """上位概念を推移的にたどって列挙する（自身は含まない）。"""
        result: list[str] = []
        seen: set[str] = {concept_id}
        current = self._concepts.get(concept_id)
        while current and current.broader:
            nxt = current.broader
            if nxt in seen:
                break  # 循環防止
            seen.add(nxt)
            result.append(nxt)
            current = self._concepts.get(nxt)
        return result

    def resolve(self, consultation: str) -> list[ConceptMatch]:
        """相談文を走査し、表層語の部分一致で概念を解決する。

        各概念につき、相談文に出現した表層語を集計しスコア化する。
        スコア = マッチした表層語数 + 最長一致長の寄与（簡易）。
        照合は正規化後に行い、根拠語(matched_surface)は相談文の原文表記
        （最初の出現箇所）で返す。
        """
        norm_text, index_map = self._normalize_with_map(consultation)
        matches: dict[str, ConceptMatch] = {}

        for surface_key, concept_ids in self._surface_index.items():
            if not surface_key:
                continue
            pos = norm_text.find(surface_key)
            if pos >= 0:
                start = index_map[pos]
                end = index_map[pos + len(surface_key) - 1] + 1
                original = consultation[start:end]
                for cid in concept_ids:
                    c = self._concepts[cid]
                    m = matches.get(cid)
                    if m is None:
                        m = ConceptMatch(
                            concept_id=cid,
                            pref_label=c.pref_label,
                            indicates_crimes=list(c.indicates_crimes),
                        )
                        matches[cid] = m
                    if original not in m.matched_surface:
                        m.matched_surface.append(original)
                    # 長い表層語ほど高スコア（誤マッチ抑制）
                    m.score += 1.0 + len(surface_key) * 0.1

        return sorted(matches.values(), key=lambda x: x.score, reverse=True)
