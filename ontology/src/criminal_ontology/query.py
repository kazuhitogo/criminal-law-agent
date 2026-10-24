"""検索API: 相談文 → 概念 → 罪候補の2段階解決 + SPARQL/推論。

グラフ構成:
  schema.ttl + build/criminal_law.ttl + build/semantics.ttl を1グラフに統合し、
  owlrl で RDFS/OWL-RL 推論を適用する（subClassOf 連鎖・inverseOf・推移律）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import owlrl
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from .build import (
    SCHEMA_PATH,
    build_all,
    load_concepts,
)
from .semantics import SemanticLayer

CL = Namespace("https://example.org/criminal-law#")

_PKG_DIR = Path(__file__).resolve().parent
_ONTOLOGY_ROOT = _PKG_DIR.parent.parent
BUILD_DIR = _ONTOLOGY_ROOT / "build"


@dataclass
class CrimeCandidate:
    crime_id: str
    label: str
    article: str
    category: str
    penalties: list[str] = field(default_factory=list)
    score: float = 0.0
    via_concepts: list[str] = field(default_factory=list)


@dataclass
class CrimeDetail:
    crime_id: str
    label: str
    article: str
    category: str
    legal_interest: str
    statute_text: str
    elements: list[dict] = field(default_factory=list)
    penalties: list[dict] = field(default_factory=list)
    related_to: list[str] = field(default_factory=list)


class CriminalLawKB:
    """刑法オントロジーの検索窓口。"""

    def __init__(self, graph: Graph, semantic_layer: SemanticLayer):
        self.g = graph
        self.sl = semantic_layer

    @classmethod
    def load(cls, *, apply_reasoning: bool = True, auto_build: bool = True) -> "CriminalLawKB":
        """schema + data + semantics を統合ロードして推論を適用する。"""
        crimes_ttl = BUILD_DIR / "criminal_law.ttl"
        sem_ttl = BUILD_DIR / "semantics.ttl"
        if auto_build and (not crimes_ttl.exists() or not sem_ttl.exists()):
            build_all()

        g = Graph()
        g.parse(str(SCHEMA_PATH), format="turtle")
        g.parse(str(crimes_ttl), format="turtle")
        g.parse(str(sem_ttl), format="turtle")

        if apply_reasoning:
            # RDFS + OWL-RL クロージャ（subClassOf, inverseOf, TransitiveProperty 等）
            owlrl.DeductiveClosure(owlrl.RDFS_OWLRL_Semantics).expand(g)

        sl = SemanticLayer(load_concepts())
        return cls(g, sl)

    # ----------------------------------------------------------------
    # セマンティックレイヤー解決
    # ----------------------------------------------------------------
    def resolve_concepts(self, text: str) -> list[dict]:
        """相談文を概念へ正規化する。"""
        matches = self.sl.resolve(text)
        return [
            {
                "concept_id": m.concept_id,
                "pref_label": m.pref_label,
                "matched_surface": m.matched_surface,
                "indicates_crimes": m.indicates_crimes,
                "score": round(m.score, 2),
            }
            for m in matches
        ]

    # ----------------------------------------------------------------
    # 2段階検索: 相談文 → 概念 → 罪候補
    # ----------------------------------------------------------------
    def search_by_text(self, text: str) -> list[CrimeCandidate]:
        """概念経由で罪候補を解決し、スコア順に返す。"""
        concept_matches = self.sl.resolve(text)
        # crime_id -> 集約候補
        agg: dict[str, CrimeCandidate] = {}

        for cm in concept_matches:
            for crime_id in cm.indicates_crimes:
                cand = agg.get(crime_id)
                if cand is None:
                    label = self._label(crime_id)
                    article = self._article_number(crime_id)
                    category = self._direct_category(crime_id)
                    cand = CrimeCandidate(
                        crime_id=crime_id,
                        label=label,
                        article=article,
                        category=category,
                        penalties=self._penalty_notes(crime_id),
                    )
                    agg[crime_id] = cand
                cand.score += cm.score
                cand.via_concepts.append(cm.concept_id)

        return sorted(agg.values(), key=lambda c: c.score, reverse=True)

    # ----------------------------------------------------------------
    # 罪詳細
    # ----------------------------------------------------------------
    def get_crime(self, crime_id: str) -> CrimeDetail | None:
        c_uri = CL[crime_id]
        if (c_uri, RDF.type, None) not in self.g:
            return None

        label = self._label(crime_id)
        article = self._article_number(crime_id)
        category = self._direct_category(crime_id)
        legal_interest = self._one_literal(c_uri, CL.protectsLegalInterest)
        statute = self._statute_text(crime_id)

        elements = []
        for e_uri in self.g.objects(c_uri, CL.hasElement):
            etype = self._one_literal(e_uri, CL.elementType)
            desc = self._one_label(e_uri)
            keywords = [str(k) for k in self.g.objects(e_uri, CL.hasKeyword)]
            elements.append({"type": etype, "desc": desc, "keywords": keywords})

        penalties = []
        for p_uri in self.g.objects(c_uri, CL.hasPenalty):
            penalties.append(
                {
                    "type": self._one_literal(p_uri, CL.penaltyType),
                    "min": self._one_int(p_uri, CL.minValue),
                    "max": self._one_int(p_uri, CL.maxValue),
                    "unit": self._one_literal(p_uri, CL.unit),
                    "note": self._one_label_or_literal(p_uri, CL.note),
                }
            )

        related = [self._local_name(o) for o in self.g.objects(c_uri, CL.relatedTo)]

        return CrimeDetail(
            crime_id=crime_id,
            label=label,
            article=article,
            category=category,
            legal_interest=legal_interest,
            statute_text=statute,
            elements=elements,
            penalties=penalties,
            related_to=related,
        )

    # ----------------------------------------------------------------
    # カテゴリ一覧（RDFS/OWL 推論を利用）
    # ----------------------------------------------------------------
    def list_categories(self) -> list[dict]:
        """罪カテゴリ（Crime のサブクラス）と所属罪数を返す。

        推論適用後は subClassOf 連鎖で上位カテゴリ型も付くため、
        count は推論込みの全所属数、direct_count は直接型の数を返す。
        leaf=True は下位カテゴリを持たない最下層カテゴリ。
        """
        q = """
        PREFIX cl: <https://example.org/criminal-law#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?cat ?label WHERE {
            ?cat rdfs:subClassOf cl:Crime .
            OPTIONAL { ?cat rdfs:label ?label . }
        }
        """
        results: dict[str, dict] = {}
        for row in self.g.query(q):
            name = self._local_name(row.cat)
            # Crime 自身・OWL 由来の疑似クラス（Nothing 等）・CL 名前空間外を除外
            if name == "Crime" or not str(row.cat).startswith(str(CL)):
                continue
            if name in ("Nothing",):
                continue
            label = str(row.label) if row.label else name
            results.setdefault(name, {"id": name, "label": label})

        # 件数集計: count=推論込み所属総数、direct_count=直接型で収録した罪数
        for name, entry in results.items():
            cat_uri = CL[name]
            total = 0
            direct = 0
            for s in self.g.subjects(RDF.type, cat_uri):
                # クラス（サブクラス定義を持つ）を除き、インスタンス（罪）のみ数える
                if (s, RDFS.subClassOf, None) in self.g:
                    continue
                total += 1
                if self._direct_category(self._local_name(s)) == name:
                    direct += 1
            entry["count"] = total
            entry["direct_count"] = direct
            # leaf 判定: 自分を上位とするカテゴリが存在しないか
            has_subcat = any(
                (CL[other], RDFS.subClassOf, cat_uri) in self.g
                for other in results
                if other != name
            )
            entry["leaf"] = not has_subcat

        return sorted(results.values(), key=lambda x: x["id"])

    def is_subclass_inferred(self, crime_id: str, superclass: str) -> bool:
        """推論により crime が superclass 型を持つか確認する（推論テスト用）。"""
        return (CL[crime_id], RDF.type, CL[superclass]) in self.g

    # ----------------------------------------------------------------
    # 可視化用: 実行SPARQL と サブグラフ(トリプル)抽出
    # ----------------------------------------------------------------
    def crime_subgraph(self, crime_id: str) -> dict:
        """罪とその直接の周辺（条文・構成要件・法定刑・概念）を SPARQL CONSTRUCT で
        サブグラフとして抽出する。

        戻り値:
          sparql  : 実行した CONSTRUCT クエリ文字列
          turtle  : 抽出サブグラフの Turtle 表現
          triples : [{s, p, o}] の簡約トリプル配列（表示用, ローカル名に短縮）
        """
        sparql = f"""\
PREFIX cl:   <https://example.org/criminal-law#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>

CONSTRUCT {{
  cl:{crime_id} ?p ?o .
  ?o ?p2 ?o2 .
  ?concept cl:indicatesCrime cl:{crime_id} ;
           skos:prefLabel ?clabel .
}}
WHERE {{
  {{
    cl:{crime_id} ?p ?o .
    # 推論で派生する冗長トリプル（owl:Thing 型付け・sameAs 自己参照等）を除外
    FILTER(?p != rdf:type || STRSTARTS(STR(?o), STR(cl:)))
    FILTER(?p NOT IN (
      <http://www.w3.org/2002/07/owl#sameAs>
    ))
  }}
  UNION {{
    cl:{crime_id} ?pp ?o .
    FILTER(?pp IN (cl:definedIn, cl:hasElement, cl:hasPenalty))
    ?o ?p2 ?o2 .
    FILTER(STRSTARTS(STR(?p2), STR(cl:)) || ?p2 = rdfs:label)
  }}
  UNION {{
    ?concept cl:indicatesCrime cl:{crime_id} .
    ?concept skos:prefLabel ?clabel .
  }}
}}
"""
        sub = self.g.query(sparql).graph  # CONSTRUCT の結果グラフ
        sub.bind("cl", CL)
        sub.bind("rdfs", RDFS)
        sub.bind("skos", SKOS)

        def _is_noise(s: str, p: str, o: str) -> bool:
            # 推論由来の冗長トリプルを表示から除く
            if p == "rdf:type" and o in ("cl:Entity",) :
                return False  # cl:Entity は階層として残す
            if p == "rdf:type" and not o.startswith("cl:"):
                return True   # owl:Thing / rdfs:Resource など
            if "sameAs" in p:
                return True
            return False

        triples = []
        for s, p, o in sub:
            ss, sp, so = self._short(s), self._short(p), self._short(o)
            if _is_noise(ss, sp, so):
                continue
            triples.append({"s": ss, "p": sp, "o": so})
        turtle = sub.serialize(format="turtle")
        triples.sort(key=lambda t: (t["s"], t["p"], t["o"]))
        return {"sparql": sparql, "turtle": turtle, "triples": triples}

    def search_by_text_traced(self, text: str) -> dict:
        """search_by_text に加え、概念解決の根拠・実行SPARQL・候補罪のサブグラフを付す。

        戻り値:
          candidates : search_by_text と同等（dict 配列）
          concepts   : 解決された概念
          sparql     : 概念→罪 を表す例示 SPARQL（SELECT）と各罪の CONSTRUCT
          subgraphs  : {crime_id: crime_subgraph(...)} 候補ごとのサブグラフ
        """
        concepts = self.resolve_concepts(text)
        cands = self.search_by_text(text)

        # 概念 → 罪 を表現する SELECT（実際の解決はセマンティックレイヤーだが、
        # 同等の問いを SPARQL で表すと以下になる、という可視化）。
        concept_ids = [c["concept_id"] for c in concepts]
        values = " ".join(f"cl:concept-{cid}" for cid in concept_ids) or "# (概念ヒットなし)"
        select_sparql = f"""\
PREFIX cl:   <https://example.org/criminal-law#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?concept ?crime ?label WHERE {{
  VALUES ?concept {{ {values} }}
  ?concept cl:indicatesCrime ?crime .
  ?crime rdfs:label ?label .
}}
"""
        subgraphs = {c.crime_id: self.crime_subgraph(c.crime_id) for c in cands}

        return {
            "concepts": concepts,
            "candidates": [
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
            ],
            "sparql": select_sparql,
            "subgraphs": subgraphs,
        }

    # ----------------------------------------------------------------
    # 内部ヘルパ
    # ----------------------------------------------------------------
    def _local_name(self, uri: URIRef) -> str:
        return str(uri).split("#")[-1]

    def _short(self, term: object) -> str:
        """URI は接頭辞付き短縮形に、リテラルはそのまま文字列化する（表示用）。"""
        s = str(term)
        if s.startswith(str(CL)):
            return "cl:" + s[len(str(CL)) :]
        if s.startswith(str(RDFS)):
            return "rdfs:" + s[len(str(RDFS)) :]
        if s.startswith(str(SKOS)):
            return "skos:" + s[len(str(SKOS)) :]
        if s.startswith(str(RDF)):
            return "rdf:" + s[len(str(RDF)) :]
        return s

    def _label(self, crime_id: str) -> str:
        return self._one_label(CL[crime_id]) or crime_id

    def _one_label(self, uri: URIRef) -> str:
        for o in self.g.objects(uri, RDFS.label):
            return str(o)
        return ""

    def _one_label_or_literal(self, uri: URIRef, pred: URIRef) -> str:
        for o in self.g.objects(uri, pred):
            return str(o)
        return ""

    def _one_literal(self, uri: URIRef, pred: URIRef) -> str:
        for o in self.g.objects(uri, pred):
            return str(o)
        return ""

    def _one_int(self, uri: URIRef, pred: URIRef) -> int | None:
        for o in self.g.objects(uri, pred):
            try:
                return int(o)
            except (TypeError, ValueError):
                return None
        return None

    def _article_number(self, crime_id: str) -> str:
        for a in self.g.objects(CL[crime_id], CL.definedIn):
            return self._one_literal(a, CL.articleNumber)
        return ""

    def _statute_text(self, crime_id: str) -> str:
        for a in self.g.objects(CL[crime_id], CL.definedIn):
            return self._one_literal(a, CL.statuteText)
        return ""

    def _penalty_notes(self, crime_id: str) -> list[str]:
        notes = []
        for p in self.g.objects(CL[crime_id], CL.hasPenalty):
            n = self._one_label_or_literal(p, CL.note)
            if n:
                notes.append(n)
        return notes

    def _direct_category(self, crime_id: str) -> str:
        """罪の直接カテゴリ（最も具体的なサブクラス）を返す。

        推論適用後は上位型も付くため、他の型の subClassOf になっていない
        最下層型を選ぶ。
        """
        types = {
            self._local_name(t)
            for t in self.g.objects(CL[crime_id], RDF.type)
            if str(t).startswith(str(CL)) and self._local_name(t) != "NamedIndividual"
        }
        crime_types = {t for t in types if self._is_crime_class(t)}
        if not crime_types:
            return ""
        # 他の crime_type の上位型でないものを選ぶ
        most_specific = []
        for t in crime_types:
            has_subtype_in_set = any(
                other != t
                and (CL[other], RDFS.subClassOf, CL[t]) in self.g
                for other in crime_types
            )
            if not has_subtype_in_set:
                most_specific.append(t)
        return sorted(most_specific)[0] if most_specific else sorted(crime_types)[0]

    def _is_crime_class(self, name: str) -> bool:
        return (CL[name], RDFS.subClassOf, CL.Crime) in self.g or name == "Crime"


# --------------------------------------------------------------------
# モジュール単体実行: クエリ確認用
# --------------------------------------------------------------------
def main() -> None:
    import sys

    text = sys.argv[1] if len(sys.argv) > 1 else "財布を盗まれた"
    kb = CriminalLawKB.load()
    print(f"query: {text}")
    print("concepts:", [c["concept_id"] for c in kb.resolve_concepts(text)])
    for cand in kb.search_by_text(text):
        print(
            f"  候補: {cand.label} (第{cand.article}条) score={cand.score:.1f} "
            f"via={cand.via_concepts} 刑={cand.penalties}"
        )


if __name__ == "__main__":
    main()
