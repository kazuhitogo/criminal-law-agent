# PLAN.md — 実装計画

詳細な要件・設計は [SPEC.md](./SPEC.md) を参照。本書は実装フェーズと手順を定義する。

実装順序（ユーザー指定）:
1. オントロジー
2. エージェント
3. Web UI

技術制約（必須）:
- Python は **uv** で管理
- Web は **TypeScript + React**
- エージェントは **Strands Agents SDK**
- オントロジーは **RDF + RDFS + OWL**（rdflib + owlrl）、セマンティックレイヤー（SKOS）込み
- LLM は **Amazon Bedrock Claude Haiku 5.5**（`us.anthropic.claude-haiku-5-5-v1:0`, 環境変数で上書き可）

---

## 実装再開ガイド（コンテキストクリア後に読む）

現状: PLAN.md / SPEC.md のみ作成・コミット済み。コード未着手。

再開手順:
1. SPEC.md を通読（特に §4 オントロジー, §4.1.1 各層サンプル, §4.6 セマンティックレイヤー, §5 エージェント）
2. 本 PLAN のフェーズ1から順に着手。フェーズ順序は厳守（オントロジー → エージェント → Web）
3. 各フェーズ完了時に対応する検証（pytest / build / tsc）を実行してからコミット
4. 刑法データ（§4.5）は e-Gov 等の一次情報から転記。法定刑は拘禁刑（2025施行）反映
5. Bedrock 認証が無い環境では、エージェントはツール層まで検証し、その旨を記録して次へ

参照の優先順位: 迷ったら SPEC.md が正。Strands SDK の API は実装時に
strandsagents.com 公式ドキュメントで最新シグネチャを確認する。

---

## フェーズ 1: オントロジー構築

ゴール: 相談文キーワードから罪候補・条文・構成要件・法定刑を返せるオントロジーと検索APIを完成させる。

- [ ] 1-1. `ontology/` を uv プロジェクトとして初期化（`uv init` / `pyproject.toml`）
  - 依存: `rdflib`, `owlrl`（OWL-RL/RDFS 推論）, `pydantic`, `pyyaml`, 開発依存: `pytest`
- [ ] 1-2. RDFS/OWL スキーマ `schema/schema.ttl` 作成（SPEC §4.1-4.3）
  - クラス階層（`rdfs:subClassOf`）、プロパティ定義域/値域、
    `owl:inverseOf` / `owl:TransitiveProperty` / `owl:disjointWith` を定義
- [ ] 1-3. pydantic モデル定義（`models.py`）: Crime / Element / Penalty / Article / Concept
- [ ] 1-4. 罪データ `data/crimes.yaml` 作成（SPEC §4.5 の形式, **刑法第2編全編**）
  - 刑法各則の全章（77〜264条）を章ごとに網羅収録
  - 個人的法益・社会的法益・国家的法益すべてのカテゴリ
  - 条文原文は e-Gov 一次情報から転記。法定刑は現行（拘禁刑, 2025施行）を反映
  - 作業量が大きいため章単位で分割収録。章ごとに整合性テストを回す
- [ ] 1-5. セマンティックレイヤー `data/semantics.yaml` + `semantics.py` 作成（SPEC §4.6）
  - 概念辞書（SKOS）、同義語/言い換え、概念→罪マッピング
  - 相談文 → 概念の正規化ロジック
- [ ] 1-6. ビルダ `build.py`: YAML を検証し schema.ttl と統合して
  Turtle(`build/criminal_law.ttl`, `build/semantics.ttl`) を生成
- [ ] 1-7. 検索API `query.py`:
  - `resolve_concepts(text) -> [concept]`（セマンティックレイヤー解決）
  - `search_by_text(text) -> [candidate]`（概念経由2段階 + スコア）
  - `get_crime(crime_id) -> detail`
  - `list_categories() -> [...]`（SPARQL + RDFS/OWL 推論）
- [ ] 1-8. テスト（`pytest`）: データ整合性・スキーマ妥当性・推論・検索結果・Turtle 生成
- [ ] 1-9. 検証: `uv run pytest` が全通過。代表クエリ（「財布を盗まれた」等）で期待罪が返る

完了条件: `uv run python -m criminal_ontology.query "財布を盗まれた"` 相当で窃盗235が返り、
刑法全編が収録され、RDFS/OWL 推論とセマンティックレイヤーが機能し、テスト緑。

---

## フェーズ 2: エージェント構築

ゴール: 相談文を受け、オントロジーを使って該当罪・条文・法定刑を構造化出力で返すエージェントとAPIを完成させる。

- [ ] 2-1. `agent/` を uv プロジェクトとして初期化
  - 依存: `strands-agents`, `fastapi`, `uvicorn`, `pydantic`, ローカル依存として `ontology`
- [ ] 2-2. Strands ツール実装（`tools.py`）: `resolve_concepts` / `search_crimes_by_text` /
  `get_crime_detail` / `list_crime_categories`（フェーズ1の query を呼ぶ）
- [ ] 2-3. エージェント定義（`agent.py`）: `BedrockModel` で **Claude Haiku 5.5**
  （`us.anthropic.claude-haiku-5-5-v1:0`, 環境変数で上書き可）、
  システムプロンプト（SPEC §5.3）、構造化出力スキーマ（§5.4）
- [ ] 2-4. FastAPI（`api.py`）: `POST /consult` を実装、CORS 設定
- [ ] 2-5. テスト: ツール単体テスト（オントロジーはモック/実データ）。API はスキーマ検証
- [ ] 2-6. 検証: `uv run uvicorn` 起動 → curl で `/consult` に相談文を投げ、構造化JSONが返る
  - LLM 呼び出しは Bedrock 認証 + Haiku 5.5 モデルアクセス有効化が必要。
    未認証環境ではツール層までを検証し、その旨記録

完了条件: ローカルで `/consult` が動作し、SPEC §5.4 スキーマ準拠のレスポンスを返す。

---

## フェーズ 3: Web UI 構築

ゴール: 相談を入力し結果を表示するブラウザ画面を完成させる。

- [ ] 3-1. `web/` を Vite + React + TypeScript で初期化
- [ ] 3-2. API クライアント（`api.ts`）: `POST /consult` 型付きラッパ
- [ ] 3-3. コンポーネント: 入力フォーム / ローディング / 結果カード / 免責表示（SPEC §6.2）
- [ ] 3-4. `App.tsx` で状態管理と画面結線
- [ ] 3-5. 検証: `npm run build`（tsc 型チェック通過）、`npm run dev` でエージェントAPIと疎通し画面表示

完了条件: ブラウザで相談を入力 → エージェント経由の結果が表示される。型チェック・ビルド通過。

---

## 全体の検証・完了基準

- フェーズ1〜3それぞれの完了条件を満たす
- 各フェーズで該当するビルド/テストが通過
- 代表シナリオの end-to-end 動作:
  - 「隣人に殴られた」→ 傷害/暴行が候補
  - 「SNSで悪口を書かれた」→ 名誉毀損/侮辱が候補
  - 「貸した金が返ってこない」→ 刑法上は該当なし（民事）と説明
- 全出力に免責が付与される

## リスク・留意点

- Bedrock 認証: LLM 実行には AWS 認証が必要。未整備の場合はツール層までで検証し明記。
- 法的正確性: 本システムは情報提供であり助言ではない。条文・法定刑は一次情報に基づき、改正追従できる構造とする。
- Strands SDK の API 変更: 実装時に公式ドキュメント（strandsagents.com）で最新シグネチャを確認する。
- キーワードマッチの限界: 初期は辞書ベース。将来は埋め込み検索へ拡張可能な設計にとどめる。
