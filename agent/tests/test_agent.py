"""フェーズ2 エージェントのテスト。

- ツールはオントロジー実データで単体検証（Bedrock 不要）。
- API はスキーマ検証。LLM 呼び出し(consult)はモックで差し替える。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from criminal_agent import agent as agent_mod
from criminal_agent import api as api_mod
from criminal_agent.agent import ConsultationResult, CrimeCandidateOut
from criminal_agent.tools import (
    get_crime_detail,
    list_crime_categories,
    resolve_concepts,
    search_crimes_by_text,
)


# -------------------------------------------------------------------
# ツール単体（実オントロジー）
# -------------------------------------------------------------------
def test_tool_resolve_concepts():
    r = resolve_concepts("財布を盗まれた")
    assert any(c["concept_id"] == "property-taking" for c in r)


def test_tool_search_theft():
    r = search_crimes_by_text("財布を盗まれた")
    assert r
    assert r[0]["crime_id"] == "theft"
    assert r[0]["article"] == "235"


def test_tool_search_assault_injury():
    r = search_crimes_by_text("隣人に殴られた")
    ids = {c["crime_id"] for c in r}
    assert {"assault", "injury"} <= ids


def test_tool_search_civil_empty():
    assert search_crimes_by_text("貸した金が返ってこない") == []


def test_tool_get_crime_detail():
    d = get_crime_detail("theft")
    assert d["label"] == "窃盗罪"
    assert d["article"] == "235"
    assert len(d["elements"]) == 3
    assert len(d["penalties"]) == 2


def test_tool_get_crime_detail_unknown():
    d = get_crime_detail("does-not-exist")
    assert "error" in d


def test_tool_list_categories():
    cats = list_crime_categories()
    ids = {c["id"] for c in cats}
    assert "CrimeAgainstProperty" in ids
    assert all(c["id"] != "Nothing" for c in cats)


# -------------------------------------------------------------------
# 構造化出力スキーマ
# -------------------------------------------------------------------
def test_consultation_result_schema_defaults():
    r = ConsultationResult(summary="テスト")
    assert r.no_crime is False
    assert r.candidates == []


def test_crime_candidate_out_schema():
    c = CrimeCandidateOut(
        crime_label="窃盗罪",
        article="235",
        confidence="high",
        penalty_text="10年以下の拘禁刑又は50万円以下の罰金",
        reasoning="他人の財物を窃取したため該当しうる",
    )
    assert c.matched_elements == []


# -------------------------------------------------------------------
# API（LLM をモック）
# -------------------------------------------------------------------
def _fake_consult(text: str, model_id: str | None = None) -> ConsultationResult:
    return ConsultationResult(
        summary=f"要約: {text}",
        candidates=[
            CrimeCandidateOut(
                crime_label="窃盗罪",
                article="235",
                confidence="high",
                matched_elements=["他人の財物", "窃取"],
                missing_elements=[],
                penalty_text="10年以下の拘禁刑又は50万円以下の罰金",
                reasoning="他人の財物を窃取したため該当しうる",
            )
        ],
        no_crime=False,
    )


def test_api_health():
    client = TestClient(api_mod.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_consult_schema(monkeypatch):
    monkeypatch.setattr(api_mod, "consult", _fake_consult)
    client = TestClient(api_mod.app)
    resp = client.post("/consult", json={"text": "財布を盗まれた"})
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert "candidates" in body
    assert "no_crime" in body
    assert "disclaimer" not in body  # 免責は廃止
    assert body["candidates"][0]["crime_label"] == "窃盗罪"
    assert body["candidates"][0]["article"] == "235"


def test_api_consult_validation_error():
    client = TestClient(api_mod.app)
    resp = client.post("/consult", json={"text": ""})
    assert resp.status_code == 422  # min_length=1 違反


def test_agent_build_does_not_require_bedrock_call():
    # Agent 構築自体は AWS 呼び出しを伴わない（遅延）
    a = agent_mod.build_agent()
    assert a is not None


# -------------------------------------------------------------------
# 可視化トレース（実オントロジー, Bedrock 不要）
# -------------------------------------------------------------------
def test_trace_for_tool_search():
    trace = agent_mod._trace_for_tool(
        "search_crimes_by_text", {"consultation": "財布を盗まれた"}
    )
    assert trace is not None
    assert trace["kind"] == "search"
    assert "SELECT" in trace["sparql"]
    assert "theft" in trace["subgraphs"]


def test_trace_for_tool_detail():
    trace = agent_mod._trace_for_tool("get_crime_detail", {"crime_id": "theft"})
    assert trace is not None
    assert trace["kind"] == "detail"
    assert trace["crime_id"] == "theft"
    assert "CONSTRUCT" in trace["sparql"]
    assert trace["triples"]


def test_trace_for_tool_unknown_returns_none():
    assert agent_mod._trace_for_tool("list_crime_categories", {}) is None


# -------------------------------------------------------------------
# SSE エンドポイント（consult_stream をモック）
# -------------------------------------------------------------------
def test_api_consult_stream(monkeypatch):
    async def fake_stream(text, model_id=None):
        yield {"type": "start"}
        yield {"type": "tool_use", "name": "search_crimes_by_text", "input": {"consultation": text}}
        yield {"type": "sparql", "label": "x", "sparql": "SELECT * WHERE {}"}
        yield {"type": "graph", "crime_id": "theft", "sparql": "C", "triples": [{"s": "cl:theft", "p": "rdfs:label", "o": "窃盗罪"}], "turtle": "t"}
        yield {"type": "result", "result": {"summary": "s", "candidates": [], "no_crime": True}}
        yield {"type": "done"}

    monkeypatch.setattr(api_mod, "consult_stream", fake_stream)
    client = TestClient(api_mod.app)
    with client.stream("POST", "/consult/stream", json={"text": "財布を盗まれた"}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = "".join(resp.iter_text())

    # SSE 形式と各イベントの存在
    import json as _json

    events = [
        _json.loads(line[len("data:"):].strip())
        for line in body.splitlines()
        if line.startswith("data:")
    ]
    types = [e["type"] for e in events]
    assert types == ["start", "tool_use", "sparql", "graph", "result", "done"]
    graph_ev = next(e for e in events if e["type"] == "graph")
    assert graph_ev["triples"][0]["o"] == "窃盗罪"
