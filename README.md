# 刑法オントロジー法律相談エージェント

日本の刑法（第2編「罪」）をオントロジー化し、自然文の相談から該当しうる罪名・条文・
構成要件・法定刑を提示するエージェントシステム。

「むかついたから訴えたい」といった日常の不満のうち、実際には刑法上の犯罪構成要件を
満たさないケースは多い。本システムは構成要件をオントロジーで形式化し、

- 該当しうる罪名・条文
- 構成要件の充足状況（満たす／不足）
- 法定刑（拘禁刑・罰金の範囲）
- 「刑法上は該当なし」の判定とその理由

を構造化して返す。民事（損害賠償・慰謝料・貸金返還など）は対象外。

> 本システムは一般的な情報提供を目的としたものであり、法的助言ではありません。
> 実際の法的対応は弁護士等の専門家にご相談ください。

詳細な要件・設計は [SPEC.md](./SPEC.md)、実装計画は [PLAN.md](./PLAN.md) を参照。

---

## アーキテクチャ

```
┌─────────────────────────────────────┐
│  web/    TypeScript + React (Vite)   │  相談入力・結果表示
└───────────────┬─────────────────────┘
                │ HTTP (POST /consult)
┌───────────────▼─────────────────────┐
│  agent/  Python / FastAPI            │  Strands Agents SDK
│          + Amazon Bedrock            │  Claude Haiku 5.5
│          （Strands ツール 4種）       │  構造化出力
└───────────────┬─────────────────────┘
                │ 検索API呼び出し
┌───────────────▼─────────────────────┐
│  ontology/  Python (rdflib + owlrl)  │  RDF/RDFS/OWL + SKOS
│             刑法オントロジー          │  概念経由2段階検索・推論
└──────────────────────────────────────┘
```

| ディレクトリ | 役割 | 主技術 |
|---|---|---|
| `ontology/` | 刑法オントロジーと検索API | rdflib, owlrl, pydantic, YAML→Turtle |
| `agent/` | 相談エージェントと REST API | Strands Agents SDK, FastAPI, Bedrock |
| `web/` | ブラウザ UI | React, TypeScript, Vite |

---

## 必要環境

- [uv](https://docs.astral.sh/uv/)（Python 管理）
- Python 3.13+
- Node.js 20+ / npm
- Amazon Bedrock へのアクセス（LLM 実行時のみ）
  - Claude Haiku 5.5 のモデルアクセスが有効なこと
  - オントロジー検索自体はオフラインで動作する

---

## セットアップと起動

### クイックスタート（コマンド一発）

agent API と web UI を 1 コマンドでまとめて起動する。初回は依存解決と
オントロジービルドも自動で行う（冪等）。

```bash
AWS_PROFILE=<your-profile> ./run.sh
```

- 起動後、ブラウザで `http://127.0.0.1:5173` を開く。
- `Ctrl+C` で両サーバをまとめて停止する。
- AWS 認証が不要な確認（オントロジー検索のみ）なら `AWS_PROFILE` は省略可。
  ただし `POST /consult` の LLM 応答には Bedrock 認証が必要。

環境変数で挙動を調整できる（いずれも任意）:

| 環境変数 | 用途 | 既定値 |
|---|---|---|
| `AGENT_PORT` | agent API ポート | `8099` |
| `WEB_PORT` | web 開発サーバポート | `5173` |
| `SKIP_SETUP` | `1` で依存解決/ビルドを省略し高速起動 | `0` |
| `AWS_PROFILE` / `AWS_REGION` | Bedrock 認証・リージョン | boto3 既定 |

個別に起動したい場合は以下の各手順を使う。

### 1. オントロジー（検索エンジン層）

```bash
cd ontology
uv sync
uv run python -m criminal_ontology.build      # YAML → Turtle 生成
uv run pytest                                  # テスト
uv run python -m criminal_ontology.query "財布を盗まれた"   # 単体確認
```

### 2. エージェント API

```bash
cd agent
uv sync
uv run pytest                                  # ツール・API テスト（Bedrock 不要）

# サーバ起動（既定ポート 8099）
AWS_PROFILE=<your-profile> uv run uvicorn criminal_agent.api:app --port 8099
```

`POST /consult` の実行には Amazon Bedrock の認証が必要。認証は環境変数で与える
（下記「認証とモデル設定」参照）。リポジトリにプロファイル名・認証情報は含めない。

動作確認:

```bash
curl -X POST http://127.0.0.1:8099/consult \
  -H "Content-Type: application/json" \
  -d '{"text":"財布を盗まれた"}'
```

### 3. Web UI

```bash
cd web
npm install
npm run dev        # 開発サーバ（http://localhost:5173）
npm run build      # 型チェック + 本番ビルド
```

ブラウザで `http://localhost:5173` を開き、相談文を入力する。
エージェント API（既定 `http://127.0.0.1:8099`）に接続する。

---

## 認証とモデル設定

認証・リージョン・モデルは**すべて環境変数で与える**。リポジトリには固定しない。

| 環境変数 | 用途 | 既定値 |
|---|---|---|
| `AWS_PROFILE` | 使用する AWS プロファイル | boto3 の既定解決 |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | Bedrock のリージョン | プロファイル設定値 |
| `CRIMINAL_AGENT_MODEL_ID` | Bedrock モデル ID | `global.anthropic.claude-haiku-5-5` |
| `CORS_ORIGINS` | 追加で許可する CORS オリジン（カンマ区切り） | `http://localhost:5173` ほか |
| `VITE_API_BASE`（web） | 接続先 API ベース URL | `http://127.0.0.1:8099` |

例（名前付きプロファイルを使う場合）:

```bash
export AWS_PROFILE=your-profile
uv run uvicorn criminal_agent.api:app --port 8099
```

> モデル ID の既定は `global.` プレフィックス（リージョン非依存の推論プロファイル）。
> リージョンやアカウントで利用可能なプロファイルが異なるため、
> 必要に応じて `CRIMINAL_AGENT_MODEL_ID` で上書きする。
> Claude Haiku 5.5 は `temperature` を受け付けないため指定していない。

---

## API

### `POST /consult`

リクエスト:

```json
{ "text": "相談文" }
```

レスポンス（`ConsultationResult`）:

```json
{
  "summary": "相談内容の要約",
  "candidates": [
    {
      "crime_label": "窃盗罪",
      "article": "235",
      "confidence": "high",
      "matched_elements": ["他人の財物", "窃取"],
      "missing_elements": [],
      "penalty_text": "10年以下の拘禁刑又は50万円以下の罰金",
      "reasoning": "〜のため該当しうる"
    }
  ],
  "no_crime": false
}
```

### `POST /consult/stream`（ストリーミング / SSE）

`/consult` と同じリクエストを受け、処理過程を Server-Sent Events で逐次配信する。
Web UI はこちらを使い、AI の思考回路・実行内容を可視化する。

各イベントは `data: <JSON>\n\n` 形式。`type` で種別を判別する:

| type | 内容 |
|---|---|
| `start` | 処理開始 |
| `reasoning` | モデルの思考（extended thinking）の断片 |
| `token` | 回答本文のテキスト断片（ストリーミング） |
| `tool_use` | ツール呼び出し（`name`, `input`） |
| `sparql` | 実行した SPARQL（ツール呼び出しに対応） |
| `graph` | 取得したナレッジグラフのサブグラフ（`triples`, `turtle`） |
| `tool_result` | ツール実行結果の要約 |
| `result` | 最終構造化結果（`ConsultationResult`） |
| `done` | 完了 |
| `error` | エラー |

ツール呼び出しを検知した時点で、オントロジー層から対応する SPARQL と
サブグラフ（罪・条文・構成要件・法定刑・概念のトリプル）を取得して流す。
LLM に渡すツール出力は軽量に保ち、可視化用データはストリーム側で別に付与する。

### `GET /health`

稼働確認。`{"status": "ok"}` を返す。

---

## 代表的な動作例

| 相談文 | 判定 |
|---|---|
| 財布を盗まれた | 窃盗罪（235条） |
| 隣人に殴られた | 暴行罪（208条）／傷害罪（204条） |
| SNSで悪口を書かれた | 名誉毀損罪（230条）／侮辱罪（231条） |
| 貸した金が返ってこない | 刑法上は該当なし（民事の問題） |

---

## オントロジーの構成

- **RDFS/OWL スキーマ** (`ontology/schema/schema.ttl`): 罪のクラス階層、プロパティの
  定義域・値域、`owl:inverseOf` / `TransitiveProperty` / `disjointWith` 等。
- **罪データ** (`ontology/data/crimes.yaml`): 刑法第2編を章横断で収録。
  条文原文・構成要件・法定刑（拘禁刑, 2025年施行を反映）。
- **セマンティックレイヤー** (`ontology/data/semantics.yaml`): SKOS 概念辞書。
  日常語（「殴られた」等）を法律概念へ正規化し、概念→罪へ橋渡しする。
- **検索 API** (`ontology/src/criminal_ontology/query.py`): 相談文 → 概念 → 罪候補の
  2段階解決。owlrl による RDFS/OWL-RL 推論でクラス階層を補う。

YAML を人が編集し、`build.py` が Turtle（`ontology/build/*.ttl`）へ変換する二層構成。

---

## テスト

```bash
cd ontology && uv run pytest     # オントロジー（データ整合性・推論・検索）
cd agent    && uv run pytest     # エージェント（ツール単体・API スキーマ）
cd web      && npm run build     # 型チェック + ビルド
```

エージェントのテストは Bedrock を呼ばない（ツール層は実オントロジー、
LLM 呼び出しはモック）。

---

## 制約・留意点

- 対象は刑法第2編の罪のみ。民事・特別刑法・刑法総則は対象外（拡張可能な構造）。
- 条文・法定刑は e-Gov 等の一次情報に基づく。改正追従できるようデータとロジックを分離。
- キーワード／概念マッチは辞書ベース。将来的に埋め込み検索へ拡張可能。
- 本システムは情報提供ツールであり、弁護士による法的助言の代替ではない。
