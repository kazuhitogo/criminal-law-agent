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
from criminal_ontology.semantics import SemanticLayer, generate_label_concepts

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 刑法第2編（77〜264条）で罪を定める条の一覧（SPEC §2）。
# e-Gov 法令データ（140AC0000000045、2026-10 時点）から、未遂・親告罪・刑の減免・
# 特例・準用・没収・削除の条を除いたもの。法改正時は scripts/egov_statutes.py list で更新する。
PART2_CRIME_ARTICLES = """
77 78 79 81 82 88 92 93 94 95 95の2 96 96の2 96の3 96の4 96の5 96の6 97 98 99 100 101
103 104 105の2 106 107 108 109 110 111 113 114 116 117 117の2 118 119 120 121 122 123
124 125 126 127 129 130 133 134 136 137 138 139 140 142 143 144 145 146 147 148 149 150
152 153 154 155 156 157 158 159 160 161 161の2 162 163 163の2 163の3 163の4 164 165 166
167 168の2 168の3 169 171 172 174 175 176 177 179 181 182 183 184 185 186 187 188 189 190
191 192 193 194 195 196 197 197の2 197の3 197の4 198 199 201 202 204 205 206 208 208の2
209 210 211 212 213 214 215 216 217 218 219 220 221 222 223 224 225 225の2 226 226の2
226の3 227 228の3 230 231 233 234 234の2 235 235の2 236 237 238 239 240 241 246 246の2
247 248 249 252 253 254 256 258 259 260 261 262 262の2 263
""".split()


# -------------------------------------------------------------------
# データ整合性
# -------------------------------------------------------------------
def test_crimes_yaml_valid():
    data = yaml.safe_load((DATA_DIR / "crimes.yaml").read_text(encoding="utf-8"))
    cf = CrimesFile(**data)
    assert len(cf.crimes) == len(PART2_CRIME_ARTICLES)


def test_articles_match_part2_list():
    """収録の条番号が、第2編で罪を定める条の一覧と過不足なく一致すること（1 条 = 1 罪）。"""
    articles = [c.article for c in load_crimes()]
    assert len(articles) == len(set(articles)), "同じ条が複数の罪に分かれている"
    expected = set(PART2_CRIME_ARTICLES)
    assert set(articles) - expected == set(), "第2編の一覧に無い条を収録している"
    assert expected - set(articles) == set(), "未収録の条がある"


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
    assert len(sf.concepts) >= len(VALID_CATEGORIES)
    ids = [c.id for c in sf.concepts]
    assert len(ids) == len(set(ids))


def test_every_crime_indicated_by_concept():
    """どの概念からも指されない罪は検索に出ないため、すべての罪が 1 つ以上の概念から指されること。

    罪名の生成概念で自明に満たされないよう、手書き概念（semantics.yaml）だけで判定する。
    """
    indicated = {cid for c in load_concepts() for cid in c.indicates_crimes}
    orphans = {c.id for c in load_crimes()} - indicated
    assert orphans == set(), f"概念から指されない罪: {sorted(orphans)}"


def test_surfaces_at_least_two_chars():
    """表層語（prefLabel / altLabel）は正規化後に 2 文字以上（1 文字語の誤マッチ防止）。"""
    short = [
        (c.id, s)
        for c in load_concepts()
        for s in [c.pref_label, *c.alt_labels]
        if len(SemanticLayer._normalize(s)) < 2
    ]
    assert short == []


def test_related_to_refs_exist():
    ids = {c.id for c in load_crimes()}
    for c in load_crimes():
        for r in c.related_to:
            assert r in ids, f"{c.id} の related_to が未知の罪 {r} を参照"


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
# 罪名の生成概念（SPEC §4.5）
# -------------------------------------------------------------------
def test_label_concepts_generated():
    generated = generate_label_concepts(load_crimes(), load_concepts())
    by_crime = {c.indicates_crimes[0]: c for c in generated}
    theft = by_crime["theft"]
    assert theft.id == "label-theft"
    assert theft.pref_label == "窃盗罪"
    assert theft.alt_labels == ["窃盗"]
    assert all(len(c.indicates_crimes) == 1 for c in generated)


def test_label_concepts_stem_rules():
    """語は 2 文字以上、手書き概念の正式名・表層語と重複しない、id は手書きと衝突しない。"""
    handwritten = load_concepts()
    taken = {SemanticLayer._normalize(s) for c in handwritten for s in [c.pref_label, *c.alt_labels]}
    hand_ids = {c.id for c in handwritten}
    for c in generate_label_concepts(load_crimes(), handwritten):
        stem = SemanticLayer._normalize(c.alt_labels[0])
        assert len(stem) >= 2
        assert stem not in taken, f"{c.id} の語 {stem} が手書き概念と重複"
        assert c.id not in hand_ids


def test_label_concepts_short_and_duplicate_skipped():
    crimes = load_crimes()[:1]
    crime = crimes[0].model_copy(update={"label": "X罪"})
    assert generate_label_concepts([crime], []) == []
    crime = crimes[0].model_copy(update={"label": "窃盗罪"})
    hand = [Concept(id="h", pref_label="窃盗")]
    assert generate_label_concepts([crime], hand) == []


def test_label_concepts_in_ttl(tmp_path):
    from criminal_ontology.build import build_all

    paths = build_all(out_dir=tmp_path)
    assert "concept-label-theft" in paths["semantics"].read_text(encoding="utf-8")


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


@pytest.mark.parametrize(
    ("text", "crime_id"),
    [
        ("差し押さえを逃れるために財産を隠した", "property-damage-to-obstruct-execution"),
        ("公共の工事の入札で談合した", "obstruction-of-public-auction"),
        ("隣の空き家に放火された", "arson-uninhabited"),
        ("拾った財布をそのまま自分のものにした", "embezzlement-of-lost-property"),
        ("万引き犯を捕まえようとしたら殴られた", "constructive-robbery"),
        ("他人のIDでネットバンキングから不正送金された", "computer-fraud"),
    ],
)
def test_search_added_crimes_top(kb: CriminalLawKB, text: str, crime_id: str):
    """全罪収録で追加した罪が、日常語の相談文で首位（同点首位を含む）に出ること。"""
    cands = kb.search_by_text(text)
    assert cands
    top = {c.crime_id for c in cands if c.score == pytest.approx(cands[0].score)}
    assert crime_id in top


@pytest.mark.parametrize(
    "text", ["怒りが爆発した", "喧嘩を売られた", "友人を買い物に誘った", "上の階から水漏れ"]
)
def test_search_no_false_match(kb: CriminalLawKB, text: str):
    """汎用語を含むが犯罪でない相談文は、候補が出ないこと。"""
    assert kb.search_by_text(text) == []


@pytest.mark.parametrize(
    ("text", "crime_id"),
    [("窃盗された", "theft"), ("横領", "embezzlement"), ("窃盗罪にあたるか", "theft")],
)
def test_search_by_crime_name(kb: CriminalLawKB, text: str, crime_id: str):
    """法律用語・罪名（末尾の「罪」なしを含む）で検索すると、その罪が首位に出ること。"""
    cands = kb.search_by_text(text)
    assert cands
    top = {c.crime_id for c in cands if c.score == pytest.approx(cands[0].score)}
    assert crime_id in top


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
