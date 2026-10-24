"""ビルダ: crimes.yaml / semantics.yaml を検証し Turtle を生成する。

生成物:
  build/criminal_law.ttl  — 罪・条文・構成要件・法定刑（RDF データ）
  build/semantics.ttl     — SKOS 概念（セマンティックレイヤー）

schema.ttl は固定スキーマとして別管理。query 側でロード時に統合する。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, XSD

from .models import (
    ELEMENT_CLASS_MAP,
    PENALTY_CLASS_MAP,
    Concept,
    Crime,
    CrimesFile,
    SemanticsFile,
)

CL = Namespace("https://example.org/criminal-law#")

# プロジェクトルート基準のデフォルトパス
_PKG_DIR = Path(__file__).resolve().parent
_ONTOLOGY_ROOT = _PKG_DIR.parent.parent  # src/criminal_ontology -> ontology/
DATA_DIR = _ONTOLOGY_ROOT / "data"
SCHEMA_PATH = _ONTOLOGY_ROOT / "schema" / "schema.ttl"
BUILD_DIR = _ONTOLOGY_ROOT / "build"


def _bind(g: Graph) -> None:
    g.bind("cl", CL)
    g.bind("rdfs", RDFS)
    g.bind("skos", SKOS)


def _crime_uri(crime_id: str) -> URIRef:
    return CL[crime_id]


def _article_uri(number: str) -> URIRef:
    # 条番号に含まれる「の」等を URI 安全化
    safe = number.replace("の", "-")
    return CL[f"art{safe}"]


def _concept_uri(concept_id: str) -> URIRef:
    return CL[f"concept-{concept_id}"]


def build_crimes_graph(crimes: list[Crime]) -> Graph:
    """罪データを RDF グラフ化する。"""
    g = Graph()
    _bind(g)

    for crime in crimes:
        c_uri = _crime_uri(crime.id)
        g.add((c_uri, RDF.type, CL[crime.category]))
        g.add((c_uri, RDFS.label, Literal(crime.label, lang="ja")))

        # 条文
        a_uri = _article_uri(crime.article)
        g.add((c_uri, CL.definedIn, a_uri))
        g.add((a_uri, RDF.type, CL.Article))
        g.add((a_uri, CL.articleNumber, Literal(crime.article)))
        g.add((a_uri, CL.statuteText, Literal(crime.statute_text)))

        # 保護法益
        g.add((c_uri, CL.protectsLegalInterest, Literal(crime.legal_interest)))

        # 構成要件要素
        for i, el in enumerate(crime.elements):
            e_uri = CL[f"{crime.id}-el{i}"]
            el_class = ELEMENT_CLASS_MAP[el.type.value]
            g.add((e_uri, RDF.type, CL[el_class]))
            g.add((e_uri, CL.elementType, Literal(el.type.value)))
            g.add((e_uri, RDFS.label, Literal(el.desc, lang="ja")))
            for kw in el.keywords:
                g.add((e_uri, CL.hasKeyword, Literal(kw)))
            g.add((c_uri, CL.hasElement, e_uri))

        # 法定刑
        for i, pen in enumerate(crime.penalties):
            p_uri = CL[f"{crime.id}-pen{i}"]
            pen_class = PENALTY_CLASS_MAP[pen.type.value]
            g.add((p_uri, RDF.type, CL[pen_class]))
            g.add((p_uri, CL.penaltyType, Literal(pen.type.value)))
            if pen.min is not None:
                g.add((p_uri, CL.minValue, Literal(pen.min, datatype=XSD.integer)))
            if pen.max is not None:
                g.add((p_uri, CL.maxValue, Literal(pen.max, datatype=XSD.integer)))
            if pen.unit is not None:
                g.add((p_uri, CL.unit, Literal(pen.unit.value)))
            g.add((p_uri, CL.note, Literal(pen.note, lang="ja")))
            g.add((c_uri, CL.hasPenalty, p_uri))

        # 関連罪
        for rid in crime.related_to:
            g.add((c_uri, CL.relatedTo, _crime_uri(rid)))

    return g


def build_semantics_graph(concepts: list[Concept]) -> Graph:
    """SKOS 概念グラフを生成する。"""
    g = Graph()
    _bind(g)

    for c in concepts:
        c_uri = _concept_uri(c.id)
        g.add((c_uri, RDF.type, SKOS.Concept))
        g.add((c_uri, SKOS.prefLabel, Literal(c.pref_label, lang="ja")))
        for alt in c.alt_labels:
            g.add((c_uri, SKOS.altLabel, Literal(alt, lang="ja")))
        if c.broader:
            g.add((c_uri, CL.broaderConcept, _concept_uri(c.broader)))
            g.add((c_uri, SKOS.broader, _concept_uri(c.broader)))
        for crime_id in c.indicates_crimes:
            g.add((c_uri, CL.indicatesCrime, _crime_uri(crime_id)))

    return g


def load_crimes(path: Path | None = None) -> list[Crime]:
    path = path or (DATA_DIR / "crimes.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return CrimesFile(**data).crimes


def load_concepts(path: Path | None = None) -> list[Concept]:
    path = path or (DATA_DIR / "semantics.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SemanticsFile(**data).concepts


def build_all(out_dir: Path | None = None) -> dict[str, Path]:
    """全データをビルドして Turtle を書き出す。生成パスを返す。"""
    out_dir = out_dir or BUILD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    crimes = load_crimes()
    concepts = load_concepts()

    crimes_g = build_crimes_graph(crimes)
    sem_g = build_semantics_graph(concepts)

    crimes_path = out_dir / "criminal_law.ttl"
    sem_path = out_dir / "semantics.ttl"
    crimes_g.serialize(destination=str(crimes_path), format="turtle")
    sem_g.serialize(destination=str(sem_path), format="turtle")

    return {"crimes": crimes_path, "semantics": sem_path}


def main() -> None:
    paths = build_all()
    for k, v in paths.items():
        print(f"built {k}: {v}")


if __name__ == "__main__":
    main()
