"""刑法相談エージェント定義。

Strands Agent + Amazon Bedrock Claude Haiku 5.5。
ツールでオントロジーを参照し、構造化出力スキーマ(ConsultationResult)で回答する。
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel

from .tools import (
    get_crime_detail,
    list_crime_categories,
    search_crimes_by_text,
)

# モデル ID は環境変数で上書き可（リージョンにより us./apac./eu. プレフィックスが変わる）
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-5-5"

SYSTEM_PROMPT = """\
あなたは日本の刑法に関する「情報提供」を行うアシスタントです。確定的な法的助言は行いません。

役割と制約:
- 扱うのは刑事（刑法第2編の罪）のみ。民事（損害賠償・慰謝料・貸金返還など）は扱わない。
- 利用者の相談文から事実関係を抽出し、該当しうる刑法上の罪・条文・法定刑を提示する。
- 断定を避け、「該当しうる」「可能性がある」という表現を用いる。

手順（必ずツールを使って根拠を得ること）:
1. 相談文から事実関係を把握する。
2. search_crimes_by_text で候補となる罪を取得する。
   各候補の matched_surface は相談文中で該当の根拠となった語。理由の説明に用いる。
3. 候補ごとに get_crime_detail で構成要件・法定刑・条文を確認する。
4. 相談文の事実が各構成要件を満たすか（matched / missing）を評価する。
5. 該当しうる罪があれば条文番号・法定刑・理由を提示する。
   候補が無い、または明らかに民事のみの問題であれば no_crime=true とする。
   このとき summary には事実の要約に加えて、次の 2 点を平易に書く:
   - 刑法上は該当しないと考えられる理由（例: 民事上の問題である）
   - 事情によっては該当しうる場合（例: 最初から返すつもりがなく借りたなら詐欺罪）

禁止事項:
- 免責文・注意書き（「本回答は一般的な情報提供であり…」「弁護士に相談してください」等）を
  summary・reasoning を含む回答のどこにも書かない。
- summary・reasoning で触れてよい罪は、search_crimes_by_text / get_crime_detail の結果で
  確認できた罪だけ。ツール結果に無い罪を記憶から挙げない。
  「事情によっては該当しうる場合」で罪を挙げるときも、仮定の事実
  （例: 「最初から返すつもりがないのに騙されて金を貸した」）で search_crimes_by_text を呼び、
  得た候補の中から挙げる。
  仮定の事実で検索しても候補が得られなかった罪は、「確認できていない」等の断り書きを
  付けても挙げてはならない。その場合は罪名を出さず、「事情によっては該当しうる場合」
  自体を書かない。

出力はすべて日本語。各候補の confidence は構成要件の充足度に基づき high/medium/low で付す。
"""


class CrimeCandidateOut(BaseModel):
    """個別の罪候補。"""

    crime_label: str = Field(description="罪名（例: 窃盗罪）")
    article: str = Field(description="刑法の条番号（例: 235）")
    confidence: str = Field(description="確信度: high / medium / low のいずれか")
    matched_elements: list[str] = Field(
        default_factory=list, description="相談文の事実が満たすと考えられる構成要件"
    )
    missing_elements: list[str] = Field(
        default_factory=list, description="充足が確認できない・不足する構成要件"
    )
    penalty_text: str = Field(description="法定刑の説明（例: 10年以下の拘禁刑又は50万円以下の罰金）")
    reasoning: str = Field(description="該当しうる/しない理由の簡潔な説明")


class ConsultationResult(BaseModel):
    """相談への構造化回答（SPEC §5.4）。"""

    summary: str = Field(
        description=(
            "相談内容の要約。no_crime=true の場合は、刑法上は該当しないと考えられる理由と、"
            "事情によっては該当しうる場合（例: 最初から返すつもりがなく借りたなら詐欺罪）も含める"
        )
    )
    candidates: list[CrimeCandidateOut] = Field(
        default_factory=list, description="該当しうる罪の候補リスト（確信度の高い順）"
    )
    no_crime: bool = Field(
        default=False,
        description="刑法上該当する罪が無い（民事のみ等）と判断される場合 true",
    )


def build_model(model_id: str | None = None) -> BedrockModel:
    mid = model_id or os.environ.get("CRIMINAL_AGENT_MODEL_ID", DEFAULT_MODEL_ID)
    # 認証(プロファイル)・リージョンはリポジトリに固定せず、実行環境に委ねる。
    #   - 認証:   AWS_PROFILE / AWS_ACCESS_KEY_ID 等（boto3 の既定解決）
    #   - リージョン: AWS_REGION / AWS_DEFAULT_REGION、無ければプロファイル設定値
    # region_name を None にすると boto3 が上記の順で解決する。
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    # Claude Haiku 5.5 は temperature を受け付けない（deprecated）ため指定しない。
    return BedrockModel(model_id=mid, region_name=region)


def build_agent(model_id: str | None = None) -> Agent:
    """刑法相談エージェントを構築する。"""
    return Agent(
        model=build_model(model_id),
        system_prompt=SYSTEM_PROMPT,
        tools=[
            search_crimes_by_text,
            get_crime_detail,
            list_crime_categories,
        ],
    )


def consult(text: str, model_id: str | None = None) -> ConsultationResult:
    """相談文を処理し、構造化回答を返す。LLM(Bedrock)呼び出しを伴う。"""
    agent = build_agent(model_id)
    result = agent(text, structured_output_model=ConsultationResult)
    out: ConsultationResult = result.structured_output
    return out


# --------------------------------------------------------------------
# ストリーミング: 思考回路・ツール呼び出し・実行SPARQL・取得グラフ・本文を逐次配信
# --------------------------------------------------------------------
# LLM に渡すツール出力は軽量に保ちつつ、ツール呼び出しを検知した時点で
# オントロジー層から実行SPARQLとサブグラフ(トリプル)を取得し、別イベントとして流す。

# ツール名 → 可視化の種類
_SEARCH_TOOL = "search_crimes_by_text"
_DETAIL_TOOL = "get_crime_detail"


def _trace_for_tool(tool_name: str, tool_input: dict) -> dict | None:
    """ツール呼び出しに対応する SPARQL / サブグラフを KB から取得する。"""
    from .tools import get_kb

    kb = get_kb()
    try:
        if tool_name == _SEARCH_TOOL:
            consultation = tool_input.get("consultation") or ""
            traced = kb.search_by_text_traced(consultation)
            return {
                "kind": "search",
                "sparql": traced["sparql"],
                "concepts": traced["concepts"],
                "subgraphs": traced["subgraphs"],
            }
        if tool_name == _DETAIL_TOOL:
            crime_id = tool_input.get("crime_id") or ""
            sg = kb.crime_subgraph(crime_id)
            return {"kind": "detail", "crime_id": crime_id, **sg}
    except Exception:  # noqa: BLE001 - 可視化は失敗しても本処理を止めない
        return None
    return None


async def consult_stream(text: str, model_id: str | None = None):
    """相談処理をストリーミングし、イベント dict を逐次 yield する。

    yield するイベント種別（"type" キー）:
      - start        : 開始
      - reasoning    : モデルの思考テキスト（extended thinking, 断片）
      - token        : 回答本文のテキスト断片
      - tool_use     : ツール呼び出し（name, input）
      - sparql       : 実行SPARQL（ツール呼び出しに対応）
      - graph        : 取得サブグラフ（triples, turtle）
      - tool_result  : ツール実行結果（要約）
      - result       : 最終構造化結果（ConsultationResult）
      - done         : 完了
      - error        : エラー
    """
    agent = build_agent(model_id)
    seen_tool_ids: set[str] = set()

    yield {"type": "start"}
    try:
        async for ev in agent.stream_async(text, structured_output_model=ConsultationResult):
            if not isinstance(ev, dict):
                continue

            # 1) 本文トークン（構造化出力モードでも data が出る場合に対応）
            if "data" in ev and ev["data"]:
                yield {"type": "token", "text": str(ev["data"])}
                continue

            # 2) 完了メッセージ: 思考テキスト / ツール呼び出し / ツール結果
            msg = ev.get("message")
            if isinstance(msg, dict):
                role = msg.get("role")
                for block in msg.get("content", []) or []:
                    if not isinstance(block, dict):
                        continue

                    # 思考（extended thinking）
                    rc = block.get("reasoningContent")
                    if rc:
                        rtext = (
                            rc.get("reasoningText", {}).get("text")
                            if isinstance(rc, dict)
                            else None
                        )
                        if rtext:
                            yield {"type": "reasoning", "text": rtext}

                    # ツール呼び出し（assistant）
                    tu = block.get("toolUse")
                    if isinstance(tu, dict) and role == "assistant":
                        tuid = tu.get("toolUseId", "")
                        name = tu.get("name", "")
                        tinput = tu.get("input", {}) or {}
                        if tuid and tuid not in seen_tool_ids:
                            seen_tool_ids.add(tuid)
                            yield {"type": "tool_use", "name": name, "input": tinput}
                            # 対応する SPARQL / サブグラフを注入
                            trace = _trace_for_tool(name, tinput)
                            if trace and trace.get("kind") == "search":
                                yield {
                                    "type": "sparql",
                                    "label": f"{name}: 概念→罪 解決",
                                    "sparql": trace["sparql"],
                                }
                                for cid, sg in trace["subgraphs"].items():
                                    yield {
                                        "type": "graph",
                                        "crime_id": cid,
                                        "sparql": sg["sparql"],
                                        "triples": sg["triples"],
                                        "turtle": sg["turtle"],
                                    }
                            elif trace and trace.get("kind") == "detail":
                                yield {
                                    "type": "sparql",
                                    "label": f"{name}: {trace['crime_id']} サブグラフ抽出",
                                    "sparql": trace["sparql"],
                                }
                                yield {
                                    "type": "graph",
                                    "crime_id": trace["crime_id"],
                                    "sparql": trace["sparql"],
                                    "triples": trace["triples"],
                                    "turtle": trace["turtle"],
                                }

                    # ツール結果（user ロールの toolResult）
                    tr = block.get("toolResult")
                    if isinstance(tr, dict) and role == "user":
                        status = tr.get("status", "")
                        # 結果本文は大きいので要約だけ流す
                        texts = [
                            c.get("text", "")
                            for c in tr.get("content", []) or []
                            if isinstance(c, dict)
                        ]
                        summary = (texts[0] if texts else "")[:200]
                        yield {
                            "type": "tool_result",
                            "status": status,
                            "summary": summary,
                        }

            # 3) 最終構造化結果
            if "structured_output" in ev and ev["structured_output"] is not None:
                so = ev["structured_output"]
                if isinstance(so, ConsultationResult):
                    yield {"type": "result", "result": so.model_dump()}

        yield {"type": "done"}
    except Exception as e:  # noqa: BLE001 - 境界でエラーイベントに変換
        yield {"type": "error", "message": str(e)}
