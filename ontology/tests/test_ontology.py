"""フェーズ1 オントロジーのテスト。

データ整合性・スキーマ妥当性・推論・検索結果・Turtle 生成を検証する。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from rdflib import Graph

from criminal_ontology.build import (
    SCHEMA_PATH,
    build_crimes_graph,
    build_semantics_graph,
    load_concepts,
    load_crimes,
)
from criminal_ontology.models import Concept, CrimesFile, SemanticsFile, VALID_CATEGORIES
from criminal_ontology.query import CriminalLawKB
from criminal_ontology.semantics import SemanticLayer

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# -------------------------------------------------------------------
# データ整合性
# -------------------------------------------------------------------
def test_crimes_yaml_valid():
    data = yaml.safe_load((DATA_DIR / "crimes.yaml").read_text(encoding="utf-8"))
    cf = CrimesFile(**data)
    assert len(cf.crimes) >= 40  # 刑法第2編を章横断で網羅


def test_crime_ids_unique():
    crimes = load_crimes()
    ids = [c.id for c in crimes]
    assert len(ids) == len(set(ids))


def test_all_categories_covered():
    """8つの法益カテゴリすべてに少なくとも1罪収録されていること。"""
    crimes = load_crimes()
    used = {c.category for c in crimes}
    assert used == VALID_CATEGORIES


def test_every_crime_has_penalty_and_statute():
    for c in load_crimes():
        assert c.penalties, f"{c.id} に法定刑がない"
        assert c.statute_text, f"{c.id} に条文原文がない"


def test_representative_crimes_present():
    ids = {c.id for c in load_crimes()}
    for required in ["theft", "injury", "assault", "defamation", "insult", "fraud", "homicide"]:
        assert required in ids


# -------------------------------------------------------------------
# セマンティックレイヤー整合性
# -------------------------------------------------------------------
def test_semantics_yaml_valid():
    data = yaml.safe_load((DATA_DIR / "semantics.yaml").read_text(encoding="utf-8"))
    sf = SemanticsFile(**data)
    assert len(sf.concepts) >= 30


def test_concept_crime_refs_exist():
    crime_ids = {c.id for c in load_crimes()}
    for c in load_concepts():
        for cid in c.indicates_crimes:
            assert cid in crime_ids, f"概念 {c.id} が未知の罪 {cid} を参照"


def test_concept_broader_refs_exist():
    concept_ids = {c.id for c in load_concepts()}
    for c in load_concepts():
        if c.broader:
            assert c.broader in concept_ids


def test_semantic_broader_closure_no_cycle():
    sl = SemanticLayer(load_concepts())
    for c in sl.all_concepts():
        closure = sl.broader_closure(c.id)
        assert c.id not in closure  # 自己言及なし


# -------------------------------------------------------------------
# スキーマ妥当性
# -------------------------------------------------------------------
def test_schema_parses():
    g = Graph()
    g.parse(str(SCHEMA_PATH), format="turtle")
    assert len(g) > 0


def test_build_graphs_nonempty():
    cg = build_crimes_graph(load_crimes())
    sg = build_semantics_graph(load_concepts())
    assert len(cg) > 0
    assert len(sg) > 0


# -------------------------------------------------------------------
# 推論（RDFS/OWL-RL）
# -------------------------------------------------------------------
@pytest.fixture(scope="module")
def kb() -> CriminalLawKB:
    return CriminalLawKB.load()


def test_subclass_inference(kb: CriminalLawKB):
    # theft は CrimeAgainstProperty のみ明示。推論で上位型が付く
    assert kb.is_subclass_inferred("theft", "Crime")
    assert kb.is_subclass_inferred("theft", "CrimeAgainstPerson")
    assert kb.is_subclass_inferred("theft", "CrimeAgainstProperty")


def test_direct_category_is_most_specific(kb: CriminalLawKB):
    assert kb.get_crime("theft").category == "CrimeAgainstProperty"
    assert kb.get_crime("homicide").category == "CrimeAgainstLifeBody"


def test_list_categories_leaf_sum(kb: CriminalLawKB):
    cats = kb.list_categories()
    # Nothing 等が混入しない
    assert all(c["id"] != "Nothing" for c in cats)
    leaf_total = sum(c["direct_count"] for c in cats if c["leaf"])
    assert leaf_total == len(load_crimes())


# -------------------------------------------------------------------
# 検索結果
# -------------------------------------------------------------------
def test_search_theft(kb: CriminalLawKB):
    cands = kb.search_by_text("財布を盗まれた")
    assert cands
    assert cands[0].crime_id == "theft"
    assert cands[0].article == "235"
    # 根拠語: 重複なく保持される
    ms = cands[0].matched_surface
    assert "盗まれた" in ms and "財布を盗まれた" in ms
    assert len(ms) == len(set(ms))


def test_search_assault_injury(kb: CriminalLawKB):
    cands = kb.search_by_text("隣人に殴られた")
    ids = {c.crime_id for c in cands}
    assert "assault" in ids
    assert "injury" in ids


def test_search_defamation_insult(kb: CriminalLawKB):
    cands = kb.search_by_text("SNSで悪口を書かれた")
    ids = {c.crime_id for c in cands}
    assert "defamation" in ids
    assert "insult" in ids
    # 根拠語は原文表記（大文字 SNS のまま）
    ms = next(c for c in cands if c.crime_id == "defamation").matched_surface
    assert "SNSで悪口" in ms
    assert "snsで悪口" not in ms


def test_matched_surface_original_notation():
    """照合は正規化後、根拠語は原文の部分文字列（空白・記号込み）で返す。"""
    layer = SemanticLayer(
        [Concept(id="c1", pref_label="財布を盗まれた", alt_labels=["SNSで悪口"])]
    )
    ms = layer.resolve("駅で 財布を、盗まれた。昨日は SNS で悪口も")[0].matched_surface
    assert "財布を、盗まれた" in ms
    assert "SNS で悪口" in ms


def test_matched_surface_first_occurrence():
    layer = SemanticLayer([Concept(id="c1", pref_label="sns")])
    m = layer.resolve("Sns と SNS")[0]
    assert m.matched_surface == ["Sns"]
    assert m.score == pytest.approx(1.0 + 3 * 0.1)


def test_search_civil_matter_returns_empty(kb: CriminalLawKB):
    # 民事（貸金返還）は刑法概念にヒットしない
    cands = kb.search_by_text("貸した金が返ってこない")
    assert cands == []


def test_resolve_concepts(kb: CriminalLawKB):
    concepts = kb.resolve_concepts("財布を盗まれた")
    assert any(c["concept_id"] == "property-taking" for c in concepts)


def test_get_crime_detail(kb: CriminalLawKB):
    d = kb.get_crime("theft")
    assert d is not None
    assert d.label == "窃盗罪"
    assert d.article == "235"
    assert len(d.elements) == 3
    assert len(d.penalties) == 2
    assert "robbery" in d.related_to


def test_get_crime_unknown(kb: CriminalLawKB):
    assert kb.get_crime("nonexistent") is None


# -------------------------------------------------------------------
# 可視化: サブグラフ抽出 / トレース付き検索
# -------------------------------------------------------------------
def test_crime_subgraph(kb: CriminalLawKB):
    sg = kb.crime_subgraph("theft")
    assert "CONSTRUCT" in sg["sparql"]
    assert sg["turtle"]
    assert sg["triples"]
    # 主要トリプルが含まれる
    flat = {(t["s"], t["p"], t["o"]) for t in sg["triples"]}
    assert ("cl:theft", "rdfs:label", "窃盗罪") in flat
    assert ("cl:theft", "cl:definedIn", "cl:art235") in flat
    # 推論由来の冗長トリプル（owl:Thing 型付け・sameAs）は除外されている
    assert all("sameAs" not in t["p"] for t in sg["triples"])
    assert all(
        not (t["p"] == "rdf:type" and not t["o"].startswith("cl:"))
        for t in sg["triples"]
    )


def test_crime_subgraph_includes_concept(kb: CriminalLawKB):
    sg = kb.crime_subgraph("theft")
    flat = {(t["s"], t["p"], t["o"]) for t in sg["triples"]}
    assert ("cl:concept-property-taking", "cl:indicatesCrime", "cl:theft") in flat


def test_search_by_text_traced(kb: CriminalLawKB):
    r = kb.search_by_text_traced("財布を盗まれた")
    assert [c["crime_id"] for c in r["candidates"]] == ["theft"]
    assert "SELECT" in r["sparql"]
    assert "concept-property-taking" in r["sparql"]
    assert "theft" in r["subgraphs"]
    assert r["subgraphs"]["theft"]["triples"]


def test_search_by_text_traced_civil_empty(kb: CriminalLawKB):
    r = kb.search_by_text_traced("貸した金が返ってこない")
    assert r["candidates"] == []
    assert r["subgraphs"] == {}


# -------------------------------------------------------------------
# Turtle 生成（ファイル書き出し）
# -------------------------------------------------------------------
def test_build_all_writes_files(tmp_path):
    from criminal_ontology.build import build_all

    paths = build_all(out_dir=tmp_path)
    assert paths["crimes"].exists()
    assert paths["semantics"].exists()
    # 再パース可能
    g = Graph()
    g.parse(str(paths["crimes"]), format="turtle")
    g.parse(str(paths["semantics"]), format="turtle")
    assert len(g) > 0
