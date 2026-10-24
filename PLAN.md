# PLAN.md — 実装計画と進捗

詳細な仕様は [SPEC.md](./SPEC.md)、使い方は [README.md](./README.md) を参照。
本書は「過去に何をしたか」「これから何をするか」の概要を記す。

技術制約（必須）:
- Python は **uv** で管理
- Web は **TypeScript + React（Vite）**
- エージェントは **Strands Agents SDK**
- オントロジーは **RDF + RDFS + OWL**（rdflib + owlrl）、セマンティックレイヤー（SKOS）込み
- LLM は **Amazon Bedrock Claude Haiku 5.5**
  （既定モデル ID `global.anthropic.claude-haiku-5-5`, 環境変数で上書き可。temperature 非対応）
- 認証・リージョン・モデル ID はすべて環境変数で与え、リポジトリに固定しない

---

## これまでに実装したこと（完了）

実装順序はユーザー指定の「オントロジー → エージェント → Web UI」。全フェーズ完了済み。

### フェーズ 1: オントロジー（`ontology/`）— 完了
- uv プロジェクト。依存: rdflib / owlrl / pydantic / pyyaml（dev: pytest）
- RDFS/OWL スキーマ `schema/schema.ttl`（クラス階層・プロパティ定義域/値域・
  `owl:inverseOf` / `TransitiveProperty` / `disjointWith`）
- 罪データ `data/crimes.yaml`（刑法第2編を章横断で **49 罪**収録、全 8 法益カテゴリ、
  条文原文・構成要件・法定刑は拘禁刑 2025 施行を反映）
- セマンティックレイヤー `data/semantics.yaml` + `semantics.py`（SKOS 概念 40 件、
  日常語→法律概念の正規化、概念→罪マッピング）
- pydantic モデル `models.py`、ビルダ `build.py`（YAML→Turtle）
- 検索 API `query.py`（`resolve_concepts` / `search_by_text` / `get_crime` /
  `list_categories`、owlrl による RDFS/OWL-RL 推論、SPARQL CONSTRUCT による
  サブグラフ抽出 `crime_subgraph` / トレース付き検索 `search_by_text_traced`）
- テスト **26 passed**。代表クエリで期待罪を確認

### フェーズ 2: エージェント（`agent/`）— 完了
- uv プロジェクト。依存: strands-agents / strands-agents-tools / fastapi /
  uvicorn / pydantic / boto3、ローカル依存として `ontology`（editable）
- Strands ツール 4 種（`tools.py`、KB は `lru_cache` で一度だけロード）
- エージェント定義（`agent.py`、`BedrockModel`、システムプロンプト、
  構造化出力 `ConsultationResult`）
- FastAPI（`api.py`）: `POST /consult`（構造化 JSON）、`GET /health`、CORS
- **ストリーミング**: `POST /consult/stream`（SSE）。`consult_stream` が
  思考(reasoning) / ツール呼び出し / 実行 SPARQL / ナレッジグラフ(トリプル) /
  本文トークン / 最終結果 を逐次配信。LLM に渡すツール出力は軽量に保ち、
  可視化データはストリーム側で別付与
- テスト **17 passed**（ツール単体・トレース・SSE はモックで検証）

### フェーズ 3: Web UI（`web/`）— 完了
- Vite + React + TypeScript
- 型付き API クライアント `api.ts`（`consult` / SSE `consultStream`）
- コンポーネント: 入力フォーム / ローディング / 結果カード / 確信度バッジ /
  免責、AI 思考回路・実行ログ（`AgentTrace`）、ナレッジグラフ（`GraphView`、
  SVG ノード・エッジ図）、本文ストリーミング（`StreamingAnswer`）
- `npm run build`（tsc 型チェック）通過

### 運用・その他 — 完了
- `run.sh`: agent と web を 1 コマンドで起動（Ctrl+C で一括停止、初回セットアップ冪等）
- README 整備。GitHub（kazuhitogo/criminal-law-agent）へ push 済み

---

## これから実装すること（予定）: Web UI リニューアル

目的: 現状の「相談フォーム + 結果カード一覧」を、**「この出来事は刑法上の
犯罪にあたるのか」を判定する体験**へ再構成する。

> **大前提（厳守）**: 表示する情報そのものは一切増減しない。既存 API が返す
> 要素（要約 / 候補＝罪名・条番号・確信度・満たしうる構成要件・不足構成要件・
> 法定刑・理由 / 該当なし判定 / 免責、および思考・ツール・SPARQL・グラフ・
> 本文ストリーム）を変えず、**見せ方・順序・インタラクションのみ**変更する。
> 仕様は SPEC.md §6 を参照。

対象は **フロントエンド（`web/`）のみ**。ontology / agent / API は変更しない。

### フェーズ U1: 判定フレーム（骨格）
- 画面を「① 事件の入力 → ② 判定ライブビュー → ③ 判定結果」の縦フローに再編
- 送信後に入力ブロックを縮小し②へスクロール誘導
- 判定ヘッダー用の派生状態を算出（no_crime / candidates 数から導出。新データなし）
- 検証: `npm run build` 通過、表示情報が不変であること

### フェーズ U2: 判定ライブビュー（ストリーミングの劇化）
- `StepIndicator`（事実把握 → 候補抽出 → 構成要件照合 → 判定）を受信イベントで点灯
- `AgentTrace` を判定文脈のラベルへ（文言のみ。GraphView 描画は不変）
- `StreamingAnswer` を「判定文の生成」見出しに
- 検証: end-to-end で実ストリーム、ステップ点灯とグラフ表示

### フェーズ U3: 構成要件チェックカード + メーター
- `ConfidenceMeter`（confidence を同値のままメーター表示）
- `ElementChecklist`（matched=✓ / missing=？、件数比で充足ゲージ）
- `CandidateCard` を再構成（罪名・条番号・法定刑・理由は保持、ラベル文言のみ変更）
- `ResultView` に判定ヘッダー（成立しうる / あたらない）。no_crime 説明文は保持
- 検証: 代表 4 シナリオで matched/missing・ゲージ・確信度が正しく出る

### フェーズ U4: インタラクション & 仕上げ
- 結果カード → ②の対応グラフ/SPARQL へのスクロール相互リンク（crime_id で対応）
- メーター/ゲージ/ステップ/グラフノードのアニメーション（`prefers-reduced-motion` 尊重）
- アクセシビリティ（`role="meter"`・aria・キーボード）とレスポンシブ
- 検証: `npm run build`、情報不変の最終チェック（SPEC.md §6 の表と突合）

---

## 検証・完了基準

### 既存（維持）
- `cd ontology && uv run pytest`（26 passed）
- `cd agent && uv run pytest`（17 passed）
- `cd web && npm run build`（tsc 通過）
- `run.sh` で end-to-end 起動し、代表シナリオが動作:
  - 財布を盗まれた → 窃盗罪（235 条）
  - 隣人に殴られた → 暴行罪（208）/ 傷害罪（204）
  - SNSで悪口を書かれた → 名誉毀損（230）/ 侮辱（231）
  - 貸した金が返ってこない → 刑法上は該当なし（民事）
- 全出力に免責が付与される

### UI リニューアル（予定）
- 表示される情報要素が SPEC.md §6 の情報マッピング表と完全一致（増減なし）
- 判定ライブビューが段階表示され、ストリームイベントが進行ステップに対応して点灯
- 罪ごとに構成要件の充足ゲージ（matched/missing 由来）と確信度メーターが表示
- no_crime 時は判定ヘッダーで「あたらない可能性」が示され既存説明文が残る
- ナレッジグラフは既存 SVG 図のまま。`prefers-reduced-motion` でアニメ無効化
- API（ontology / agent / エンドポイント）に変更がない（`git diff --stat` で確認）

---

## 環境・起動（詳細は README.md）

- 型チェック+ビルド: `cd web && npm run build`
- dev 単体: `cd web && npm run dev -- --host 127.0.0.1 --port 5173`
  （vite は既定 IPv6 バインドのため `--host 127.0.0.1` 指定で curl 疎通可）
- end-to-end 一括: `AWS_PROFILE=<profile> ./run.sh`（agent=8099 / web=5173）
  - AWS プロファイルが SSO の場合、期限切れ時は `aws sso login --profile <profile>`
- SSE 実確認:
  ```
  curl -N -X POST http://127.0.0.1:8099/consult/stream \
    -H "Content-Type: application/json" -d '{"text":"隣人に殴られた"}'
  ```

## リスク・留意点

- **情報を増やさない制約**（UI リニューアル）: 新しい分析・スコア・文言の中身を
  足さない。メーター/ゲージは既存の confidence / matched / missing から導出するに留める。
- GraphView の描画ロジック（レイアウト・色・トリプル解釈）は変更しない。
- API を変えないため、判定ヘッダーやステップはフロント側の導出で実現する。
- Bedrock 認証: LLM 実行には AWS 認証が必要。未整備の環境ではビルド（tsc）/
  ツール層までで検証し、実ストリーム目視はスキップして記録する。
- 法的正確性: 本システムは情報提供であり助言ではない。条文・法定刑は一次情報に基づく。
