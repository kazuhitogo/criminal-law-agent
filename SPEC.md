# SPEC.md — 刑法オントロジー法律相談エージェント

## 1. 概要

日本の刑法に基づくオントロジーを構築し、ユーザーの「訴えたい」相談文を入力として、
該当しうる刑法条文・構成要件・法定刑を提示するエージェントシステム。

「むかついたから訴える」といった日常の不満のうち、実際には刑法上の犯罪構成要件を
満たさないケースが多い。本システムはオントロジーによる構成要件の形式化により、
- 該当しうる罪名・条文
- 構成要件の充足状況
- 法定刑（懲役/罰金の範囲）
- 「刑法上は該当なし」の判定とその理由

を返す。

> 民法上の論点（損害賠償、慰謝料等）は本システムの対象外。刑事のみを扱う。

## 2. スコープ

### 対象
- 日本国刑法（明治40年法律第45号）**第2編「罪」の全編（77条〜264条）を網羅収録**
  - 個人的法益: 殺人・傷害・暴行・脅迫・強要・逮捕監禁・不同意性交・住居侵入・
    名誉毀損・侮辱・業務妨害・窃盗・強盗・詐欺・恐喝・横領・背任・器物損壊 ほか
  - 社会的法益: 放火・騒乱・往来妨害・通貨偽造・文書偽造・有価証券偽造・
    わいせつ・賭博 ほか
  - 国家的法益: 内乱・外患・公務執行妨害・逃走・犯人蔵匿・証拠隠滅・偽証・
    虚偽告訴・収賄・職権濫用 ほか
  - 刑法各則の章構成を RDFS クラス階層に対応させ、全章を収録する
- 自然文の相談入力 → セマンティックレイヤーで概念化 → 構成要件マッチング →
  条文・法定刑の回答

### 非対象（初期リリース）
- 民事（不法行為、債務不履行等）
- 特別刑法（軽犯罪法、各種行政刑罰法規）… 構造上は拡張可能
- 刑法総則（未遂・共犯・正当防衛等の一般規定）… 各罪の成立評価では参照するが、
  独立した収録対象外。将来拡張可能
- 量刑の具体的予測、判例検索
- 法的助言としての確定的判断（免責を明示）

## 3. 全体アーキテクチャ

```
┌─────────────────────────────────────────────┐
│  Web UI (TypeScript + React)                 │
│  - 相談入力フォーム                           │
│  - 回答表示（条文・構成要件・法定刑）         │
└───────────────┬─────────────────────────────┘
                │ HTTP (REST/JSON)
┌───────────────▼─────────────────────────────┐
│  Agent API (Python / uv / FastAPI)           │
│  - Strands Agents SDK（Claude Haiku 5.5）    │
│  - ツール: query_ontology, get_article       │
└───────────────┬─────────────────────────────┘
                │ 自然文 → 概念
┌───────────────▼─────────────────────────────┐
│  Semantic Layer（セマンティックレイヤー）     │
│  - 自然文キーワード ⇄ オントロジー概念の対応  │
│  - 同義語/言い換え辞書、概念正規化            │
│  - ビジネス的な問い（相談意図）を SPARQL へ   │
│    橋渡しする語彙マッピング                   │
└───────────────┬─────────────────────────────┘
                │ SPARQL / 概念クエリ
┌───────────────▼─────────────────────────────┐
│  Ontology Layer (Python / uv)                │
│  - 刑法オントロジー（RDF / RDFS / OWL）       │
│  - 罪名・構成要件・法定刑・保護法益           │
│  - 推論（RDFS/OWL）+ SPARQL クエリ            │
└──────────────────────────────────────────────┘
```

## 4. オントロジー仕様

### 4.1 表現形式

**RDF + RDFS + OWL（rdflib）を採用。** 各層の役割:

- **RDF**: 個々の罪・条文・構成要件・法定刑をトリプル（主語-述語-目的語）で表現する
  データ本体。
- **RDFS**: クラス階層（`rdfs:subClassOf`）とプロパティの定義域・値域
  （`rdfs:domain` / `rdfs:range`）、ラベル（`rdfs:label`）を定義する語彙スキーマ。
  罪カテゴリの is-a 階層や保護法益の分類はここで表現。
- **OWL**: より強い意味制約と推論を担う。
  - `owl:Class` / `owl:ObjectProperty` / `owl:DatatypeProperty` で語彙を宣言
  - `owl:TransitiveProperty`（例: カテゴリ包含の推移性）
  - `owl:inverseOf`（例: `definedIn` ⇔ `defines`）
  - `owl:disjointWith`（例: 財産罪と生命身体罪のクラス排他）
  - `owl:equivalentClass` / `owl:sameAs`（別名の同一視）
  これにより「ある罪が個人的法益に対する罪か」等を明示せずとも推論で導ける。

採用理由:
- 法律の「構成要件 → 罪 → 法定刑」「罪 → 保護法益」は is-a / part-of 関係で
  素直に表現でき、オントロジーの意味論と相性が良い。
- 特別刑法・判例・民法へ拡張する際、名前空間分離とリンクが容易。
- SPARQL による宣言的クエリ + RDFS/OWL 推論でツール実装を薄くできる。

ソースは人間が書きやすい **YAML** で管理し、ビルド時に RDF(Turtle) へ変換する
二層構成とする（編集容易性 + 推論能力の両立）。RDFS/OWL スキーマ（`schema.ttl`）は
YAML とは別に固定定義として保持し、データ側 Turtle と合わせてグラフにロードする。

**名前空間**:
- 基底 IRI: `https://example.org/criminal-law#`（接頭辞 `cl:`）
- 併用語彙: `rdf:` / `rdfs:` / `owl:` / `skos:` / `xsd:`

**推論エンジン**: rdflib 単体は RDFS/OWL の推論を自動適用しない。
`owl:inverseOf` / `owl:TransitiveProperty` / `rdfs:subClassOf` 連鎖などを有効化するため、
**`owlrl`（OWL-RL / RDFS クロージャ）を依存に加え**、グラフロード後に推論を適用する。
推論を使わない単純一致検索のみで足りる場合も、クラス階層解決のため最低限 RDFS 推論は適用する。

### 4.1.1 各層に実際に書く内容（サンプル）

RDFS/OWL = スキーマ（型・ルール, ほぼ固定, `schema.ttl`）。
RDF = データ（個々の罪・条文, 罪ごとに増える, YAML→`*.ttl`）。

**RDFS（クラス階層・プロパティ定義）**:
```turtle
cl:Crime                a rdfs:Class ; rdfs:label "罪" .
cl:CrimeAgainstPerson   rdfs:subClassOf cl:Crime ; rdfs:label "個人的法益に対する罪" .
cl:CrimeAgainstProperty rdfs:subClassOf cl:CrimeAgainstPerson ; rdfs:label "財産に対する罪" .
cl:Element  a rdfs:Class . cl:Penalty a rdfs:Class . cl:Article a rdfs:Class .
cl:hasElement a rdf:Property ; rdfs:domain cl:Crime ; rdfs:range cl:Element .
cl:hasPenalty a rdf:Property ; rdfs:domain cl:Crime ; rdfs:range cl:Penalty .
cl:definedIn  a rdf:Property ; rdfs:domain cl:Crime ; rdfs:range cl:Article .
```

**OWL（推論制約）**:
```turtle
cl:hasPenalty a owl:ObjectProperty .
cl:maxYears   a owl:DatatypeProperty ; rdfs:range xsd:integer .
cl:definedIn  a owl:ObjectProperty ; owl:inverseOf cl:defines .   # 条文⇄罪 双方向
cl:broaderConcept a owl:TransitiveProperty .                      # 概念階層の推移
cl:CrimeAgainstProperty owl:disjointWith cl:CrimeAgainstLifeBody . # 法益カテゴリ排他
cl:injury owl:equivalentClass cl:bodilyHarm .                     # 別名の同一視
```

**RDF（罪インスタンス = YAML から生成）**:
```turtle
cl:theft a cl:CrimeAgainstProperty ;
    rdfs:label "窃盗罪" ;
    cl:definedIn cl:art235 ;
    cl:protectsLegalInterest cl:property-possession ;
    cl:hasElement cl:theft-object ;
    cl:hasPenalty cl:theft-pen-imprisonment , cl:theft-pen-fine .
cl:art235 a cl:Article ;
    cl:statuteText "他人の財物を窃取した者は、窃盗の罪とし、十年以下の拘禁刑又は五十万円以下の罰金に処する。" .
cl:theft-object a cl:ObjectElement ; rdfs:label "他人の財物" ; cl:hasConcept cl:concept-theft .
cl:theft-pen-imprisonment a cl:Imprisonment ; cl:maxYears 10 ; cl:note "10年以下の拘禁刑" .
```

**SKOS（セマンティックレイヤー = semantics.yaml から生成）**:
```turtle
cl:concept-theft a skos:Concept ;
    skos:prefLabel "財物の窃取" ;
    skos:altLabel "盗まれた" , "取られた" , "万引き" , "スられた" ;
    cl:indicatesCrime cl:theft .
```

> 推論で得られること: `cl:theft a cl:CrimeAgainstProperty` だけ書けば subClassOf 連鎖で
> `cl:theft a cl:Crime` が導ける。`definedIn` を書けば inverseOf で `defines` も導ける。
> 概念の `broaderConcept` は推移的にたどれる。= 書かない事実を推論が補う。

### 4.2 クラス階層

```
Entity
├── Crime（罪）
│   ├── CrimeAgainstPerson（個人的法益に対する罪）
│   │   ├── CrimeAgainstLifeBody（生命・身体）
│   │   │   例: 殺人199, 傷害204, 傷害致死205, 暴行208, 過失致死210,
│   │   │       遺棄217, 堕胎212 ほか
│   │   ├── CrimeAgainstFreedomHonor（自由・名誉・秘密）
│   │   │   例: 逮捕監禁220, 脅迫222, 強要223, 略取誘拐224,
│   │   │       不同意性交177, 住居侵入130, 信書開封133,
│   │   │       名誉毀損230, 侮辱231 ほか
│   │   └── CrimeAgainstProperty（財産）
│   │       例: 窃盗235, 強盗236, 詐欺246, 恐喝249, 横領252,
│   │           背任247, 盗品関与256, 器物損壊261 ほか
│   ├── CrimeAgainstSociety（社会的法益に対する罪）
│   │   ├── CrimeAgainstPublicSafety（公共の安全）
│   │   │   例: 騒乱106, 放火108-, 往来妨害124, 激発物破裂117 ほか
│   │   ├── CrimeAgainstPublicTrust（公共の信用）
│   │   │   例: 通貨偽造148, 文書偽造155-, 有価証券偽造162,
│   │   │       支払用カード電磁的記録163の2, 印章偽造164 ほか
│   │   └── CrimeAgainstPublicMorals（風俗・健康）
│   │       例: わいせつ175, 賭博185, 礼拝所不敬188,
│   │           飲料水汚染142 ほか
│   └── CrimeAgainstState（国家的法益に対する罪）
│       ├── CrimeAgainstStateExistence（国家存立）
│       │   例: 内乱77, 外患誘致81 ほか
│       └── CrimeAgainstStateFunction（国家作用）
│           例: 公務執行妨害95, 逃走97, 犯人蔵匿103,
│               証拠隠滅104, 偽証169, 虚偽告訴172,
│               収賄197-, 職権濫用193 ほか
├── Element（構成要件要素）
│   ├── ConductElement（行為）
│   ├── ResultElement（結果）
│   ├── ObjectElement（客体）
│   ├── CircumstanceElement（状況・付随事情）
│   └── IntentElement（故意・目的・過失）
├── Penalty（法定刑）
│   ├── DeathPenalty（死刑）
│   ├── Imprisonment（拘禁刑/懲役/禁錮）
│   └── Fine（罰金・科料）
├── LegalInterest（保護法益）
└── Article（条文）
```

> 刑法第2編（罪, 77条〜264条）の全章を対象とする。章立て（各則の編別）を
> RDFS クラス階層にそのまま対応させ、刑法全編を網羅的に収録する。

### 4.3 プロパティ（述語）

| プロパティ | 定義域 → 値域 | 意味 |
|-----------|--------------|------|
| `definedIn` | Crime → Article | 罪が規定される条文 |
| `hasElement` | Crime → Element | 構成要件要素を持つ |
| `hasPenalty` | Crime → Penalty | 法定刑を持つ |
| `requiresIntent` | Crime → IntentElement | 故意/目的の要否 |
| `protectsLegalInterest` | Crime → LegalInterest | 保護法益 |
| `relatedTo` | Crime → Crime | 関連罪（択一・加重等） |
| `hasKeyword` | Element → Literal | 自然文マッチ用キーワード |
| `hasConcept` | Element → Concept | セマンティックレイヤーの概念への参照 |
| `inChapter` | Crime → Chapter | 刑法各則の章 |

RDFS/OWL レベルでは以下も定義する。
- `rdfs:subClassOf`: 罪カテゴリの is-a 階層
- `owl:inverseOf`: `definedIn` ⇔ `defines`
- `owl:TransitiveProperty`: `broaderConcept`（上位概念の推移）
- `owl:disjointWith`: 法益カテゴリ間の排他

### 4.4 Penalty のデータモデル

```
Penalty:
  type: death | imprisonment | fine
  min: 数値（月 or 円）, 単位は unit で保持
  max: 数値（上限なしは null）
  unit: month | year | yen | null
  note: 自由記述（「10年以下の懲役」「死刑又は無期拘禁刑」等の原文）
```

### 4.5 データ項目（1罪あたり）

```yaml
- id: theft
  label: 窃盗罪
  article: "235"
  category: CrimeAgainstProperty
  legal_interest: 財産（占有）
  elements:
    - type: object
      desc: 他人の財物
      keywords: [盗む, 盗まれた, 取られた, 持ち去, 万引き, スリ, 財布, 自転車]
    - type: conduct
      desc: 窃取（占有者の意思に反する占有移転）
      keywords: [盗む, こっそり, 勝手に持って]
    - type: intent
      desc: 故意 + 不法領得の意思
      keywords: []
  penalties:
    - type: imprisonment
      max: 10
      unit: year
      note: 10年以下の拘禁刑
    - type: fine
      max: 500000
      unit: yen
      note: 50万円以下の罰金
  statute_text: "他人の財物を窃取した者は、窃盗の罪とし、十年以下の拘禁刑又は五十万円以下の罰金に処する。"
```

> 法定刑は刑法改正（拘禁刑の創設, 2025年6月施行）を反映。条文原文は e-Gov 等の
> 公開一次情報を参照し、`statute_text` に転記する。

### 4.6 セマンティックレイヤー

生の相談文（日常語）と、厳密なオントロジー語彙（法律概念）の間を橋渡しする層。
RDF グラフ上の `skos:Concept` 群と、それに紐づく語彙マッピングで構成する。

役割:
1. **概念正規化**: 「殴られた」「ボコられた」「叩かれた」→ 概念 `physical-assault` に集約。
2. **同義語/言い換え辞書**: 概念ごとに表層語リスト（`skos:altLabel`）を保持し、
   相談文の表現ゆらぎを吸収する。
3. **概念 → 罪のマッピング**: 概念から関連する罪候補へのリンク
   （`concept → indicatesCrime → Crime`）。1概念が複数罪を指しうる
   （例: `threat-of-harm` → 脅迫222 / 強要223 / 恐喝249）。
4. **問い合わせ変換**: 「訴えたい」という相談意図を、
   「どの保護法益が侵害されたか」という SPARQL クエリ可能な形へ変換する語彙を提供。

データ形式（`data/semantics.yaml`）:

```yaml
concepts:
  - id: physical-assault
    pref_label: 身体への有形力の行使
    alt_labels: [殴られた, 叩かれた, ボコられた, 蹴られた, 突き飛ばされた, 暴力]
    broader: bodily-harm          # 上位概念（推移的）
    indicates_crimes: [assault, injury]   # 暴行208 / 傷害204
  - id: threat-of-harm
    pref_label: 害悪の告知
    alt_labels: [脅された, 殺すと言われた, 脅迫, 危害を加えると]
    indicates_crimes: [intimidation, compulsion, extortion]
```

ビルド時にこの YAML も Turtle（`build/semantics.ttl`）へ変換し、SKOS 語彙として
オントロジーグラフに統合する。セマンティックレイヤーはオントロジー層内の
サブモジュール（`semantics.py`）として実装し、検索API（`query.py`）が
「相談文 → 概念 → 罪候補」の2段階解決に利用する。

セマンティックレイヤー採用の意義:
- 罪ごとの `keywords` を直接増やすより、概念を介した方が保守性・再利用性が高い。
- 「訴えたい動機（怒り・被害感情）」と「法的に保護される利益」のギャップを
  概念レベルで可視化でき、「刑法上は該当しない」の説明根拠になる。

## 5. エージェント仕様

### 5.1 使用技術
- Python（**uv** で環境・依存管理。`pyproject.toml`）
- **Strands Agents SDK**（`strands-agents`）
- モデルプロバイダ: Amazon Bedrock
  - モデル: **Claude Haiku 5.5**
  - 推論プロファイル ID を使用。既定は `global.anthropic.claude-haiku-5-5`
    （リージョン非依存）。リージョン固定が必要なら `us.` / `apac.` 等の
    プロファイルを環境変数 `CRIMINAL_AGENT_MODEL_ID` で指定する
  - 認証・リージョンは環境変数（`AWS_PROFILE` / `AWS_REGION` ほか, boto3 既定解決）
  - Claude Haiku 5.5 は `temperature` を受け付けないため指定しない
- API サーバ: FastAPI（`/consult`, `/consult/stream`, `/health`）

```python
import os
from strands import Agent
from strands.models import BedrockModel

model_id = os.environ.get("CRIMINAL_AGENT_MODEL_ID", "global.anthropic.claude-haiku-5-5")
model = BedrockModel(model_id=model_id)  # region は環境に委ねる。temperature 指定なし
```

### 5.2 エージェント構成

単一エージェント + カスタムツール。

```python
from strands import Agent, tool

@tool
def resolve_concepts(consultation: str) -> list[dict]:
    """相談文をセマンティックレイヤーで概念へ正規化する（表現ゆらぎ吸収）"""

@tool
def search_crimes_by_text(consultation: str) -> list[dict]:
    """相談文 → 概念 → 罪候補を解決して返す（概念経由の2段階検索）"""

@tool
def get_crime_detail(crime_id: str) -> dict:
    """罪IDから条文・構成要件・法定刑の詳細を取得する"""

@tool
def list_crime_categories() -> list[dict]:
    """収録している罪のカテゴリ一覧を返す"""
```

### 5.3 システムプロンプト（要旨）
- 役割: 日本の刑法に関する「情報提供」。確定的な法的助言ではない旨を必ず付す。
- 手順:
  1. 相談文から事実関係を抽出
  2. `search_crimes_by_text` で候補罪を取得
  3. 候補ごとに `get_crime_detail` で構成要件を確認
  4. 構成要件の充足/不充足を評価
  5. 該当しうる罪があれば条文・法定刑を提示。なければ「刑法上は該当しない可能性が高い」と理由を説明
- 民事論点は扱わない旨を明示。

### 5.4 構造化出力（レスポンススキーマ）

```json
{
  "summary": "相談内容の要約",
  "candidates": [
    {
      "crime_label": "脅迫罪",
      "article": "222",
      "confidence": "high | medium | low",
      "matched_elements": ["害悪の告知"],
      "missing_elements": [],
      "penalty_text": "2年以下の拘禁刑又は30万円以下の罰金",
      "reasoning": "〜のため該当しうる"
    }
  ],
  "no_crime": false,
  "disclaimer": "本回答は情報提供であり、確定的な法的助言ではありません。"
}
```

### 5.5 ストリーミング出力（SSE）

`POST /consult/stream` は `/consult` と同じ body を受け、処理過程を
Server-Sent Events で逐次配信する。各イベントは `data: <JSON>\n\n` 形式で、
`type` により種別を判別する:

| type | 内容 |
|---|---|
| `start` | 処理開始 |
| `reasoning` | モデルの思考（extended thinking）の断片 |
| `token` | 回答本文のテキスト断片 |
| `tool_use` | ツール呼び出し（`name`, `input`） |
| `sparql` | 実行した SPARQL（ツール呼び出しに対応, `label`, `sparql`） |
| `graph` | 取得したナレッジグラフのサブグラフ（`crime_id`, `triples`, `turtle`） |
| `tool_result` | ツール実行結果の要約（`status`, `summary`） |
| `result` | 最終構造化結果（§5.4 の `ConsultationResult`） |
| `done` | 完了 |
| `error` | エラー（`message`） |

ツール呼び出しを検知した時点で、オントロジー層から対応する SPARQL と
サブグラフ（罪・条文・構成要件・法定刑・概念のトリプル）を取得して流す。
LLM に渡すツール出力は軽量に保ち、可視化用データはストリーム側で別に付与する。

## 6. Web UI 仕様

### 6.1 使用技術
- **TypeScript + React**
- ビルド: Vite
- スタイル: プレーン CSS（`App.css`）。外部 UI ライブラリは追加しない
- 状態管理: React 標準（useState）。SSE は fetch + ReadableStream で購読

### 6.2 画面（現状実装）
- 単一ページ
  - ヘッダー（タイトル + 免責表示）
  - 相談入力テキストエリア + 例チップ + 送信ボタン
  - ローディング表示
  - AI 思考回路・実行ログ（思考 / ツール呼び出し / 実行 SPARQL /
    ナレッジグラフ / ツール結果）
  - 本文ストリーミング表示
  - 結果表示カード（候補罪ごとに: 罪名 / 条文 / 法定刑 / 満たしうる構成要件 /
    不足構成要件 / 該当理由 / 確信度バッジ）
  - 「該当なし」時の説明表示
  - フッター免責文

### 6.3 API 連携
- `POST /consult`  body: `{ "text": string }`、レスポンスは §5.4 の構造化出力
- `POST /consult/stream`  同じ body。SSE で §5.5 のイベントを逐次受信（UI の既定）

### 6.4 ストリーミング可視化（現状実装）
Web UI は `/consult/stream` を購読し、処理過程を逐次表示する:
- **思考回路**: `reasoning` イベント（モデルの extended thinking）
- **ツール呼び出し**: `tool_use`（ツール名・入力）/ `tool_result`（結果要約）
- **実行 SPARQL**: `sparql`（ツール呼び出しに対応する実行クエリ）
- **ナレッジグラフ**: `graph`（罪・条文・構成要件・法定刑・概念のトリプル）を
  SVG のノード・エッジ図で描画（`GraphView`）。トリプル一覧（表）も併記
- **本文ストリーミング**: `token`（回答本文のタイプライタ表示）
- **最終結果**: `result`（§5.4 の構造化結果をカード表示）

### 6.5 UI リニューアル仕様（犯罪成立判定体験・予定）

現状の「相談フォーム + 結果カード一覧」を「**この出来事は刑法上の犯罪に
あたるのか**」を判定する体験へ再構成する。実装計画は PLAN.md「これから実装すること」。

> **大前提（厳守）**: 表示する情報そのものは一切増減しない。§6.6 の情報マッピングを
> 厳守し、変更は見せ方・順序・インタラクション（ラベル文言・配置・アニメ・相互リンク）
> に限定する。ontology / agent / API は変更しない。

画面構成（単一ページ・縦フロー）:
- ヘッダー（タイトル + 免責。常時表示・文言不変）
- ① 事件の入力（旧・相談フォーム。送信ボタンは「判定を開始する」ラベル）
- ② 判定ライブビュー（ストリーミング中に出現）
  - **ステップ・インジケータ**: 「事実の把握 → 候補の抽出 → 構成要件の照合 → 判定」
    の 4 段。受信イベント種別で点灯（事実把握=start/最初の reasoning、
    候補抽出=tool_use(search_crimes_by_text)/sparql/graph、
    構成要件照合=tool_use(get_crime_detail)/graph/reasoning、判定=result）
  - 思考（検討メモ）/ ツール（参照アクション）/ SPARQL（参照クエリ）/
    ナレッジグラフ（既存 SVG 描画のまま）/ 本文（判定文の生成）
- ③ 判定結果（確定後）
  - **判定ヘッダー**: 候補ありは「犯罪が成立しうる（◯件の罪に該当の可能性）」、
    no_crime は「刑法上の犯罪にはあたらない可能性が高い」
    （no_crime と candidates 数からフロント側で導出。新しい事実は足さない）
  - 事件の要約（既存 summary）
  - 罪ごとの**構成要件チェックカード**:
    - 罪名 + 第 N 条 + **確信度メーター**（既存 confidence を同値で表示）
    - **充足ゲージ**: matched 件数 /(matched + missing) 件数の帯グラフ。
      matched=「✓ 満たしうる」、missing=「？ 要確認／不足」。各行の文字列は既存配列のまま
    - 「成立した場合の刑」（既存 penalty_text、文言不変）
    - 「判定の根拠」（既存 reasoning）
    - カードクリックで②の対応グラフ/SPARQL へスクロール（crime_id で対応づけ）
  - no_crime 時は既存説明文（民事にとどまる等）を保持

マイクロインタラクション: メーター/ゲージの出現アニメ、ステップ点灯のフェード、
グラフノードのポップ。すべて `prefers-reduced-motion` を尊重し無効時は即時表示。

アクセシビリティ: メーター/ゲージに `role="meter"` / `aria-valuenow` 等。
キーボード操作・スクリーンリーダで判定結果が読めること。

### 6.6 情報マッピング（不変であることの保証）

| 既存の情報要素 | 現 UI | リニューアル後の置き場所 | 変更 |
|---|---|---|---|
| 相談テキスト入力 | フォーム | ① 事件の入力 | 文言のみ |
| 例チップ | フォーム | ① 例で試す | 文言のみ |
| summary | 結果上部 | ③ 事件の要約 | なし |
| candidate.crime_label | カード見出し | ③ チェックカード見出し | なし |
| candidate.article | カード見出し | ③ チェックカード見出し | なし |
| candidate.confidence | バッジ | ③ 確信度メーター（同値） | 表現のみ |
| candidate.matched_elements | リスト | ③ 充足ゲージ＋✓行 | 表現のみ |
| candidate.missing_elements | リスト | ③ 充足ゲージ＋？行 | 表現のみ |
| candidate.penalty_text | カード | ③「成立した場合の刑」 | 文言ラベルのみ |
| candidate.reasoning | カード | ③「判定の根拠」 | 文言ラベルのみ |
| no_crime | 専用枠 | ③ 判定ヘッダー＋説明 | 表現のみ |
| disclaimer | フッター | フッター（＋ヘッダー） | なし |
| reasoning（stream） | AgentTrace | ② 検討メモ | 表現のみ |
| tool_use / tool_result | AgentTrace | ② 判定の進行 | 表現のみ |
| sparql | AgentTrace | ② 参照クエリ | 表現のみ |
| graph（triples/turtle） | GraphView | ② ナレッジグラフ（同描画） | なし |
| token（stream） | StreamingAnswer | ② 判定文の生成 | 表現のみ |

> データ項目の増減はゼロ。ラベル文言・配置・アニメーション・相互リンクのみを変更する。

## 7. ディレクトリ構成

```
criminal-law-agent/
├── PLAN.md
├── SPEC.md
├── ontology/                 # フェーズ1
│   ├── pyproject.toml        # uv
│   ├── data/
│   │   ├── crimes.yaml       # 罪データ（人間が編集, 刑法全編）
│   │   └── semantics.yaml    # セマンティックレイヤー概念辞書
│   ├── schema/
│   │   └── schema.ttl        # RDFS/OWL スキーマ（固定定義）
│   ├── src/criminal_ontology/
│   │   ├── __init__.py
│   │   ├── models.py         # pydantic モデル
│   │   ├── build.py          # YAML → Turtle 変換（schema.ttl と統合）
│   │   ├── semantics.py      # セマンティックレイヤー（概念正規化）
│   │   └── query.py          # SPARQL/検索 API（概念経由2段階）
│   ├── build/
│   │   ├── criminal_law.ttl  # 生成物（罪データ）
│   │   └── semantics.ttl     # 生成物（SKOS 概念）
│   └── tests/
├── agent/                    # フェーズ2
│   ├── pyproject.toml        # uv（ontology を依存に）
│   ├── src/criminal_agent/
│   │   ├── __init__.py
│   │   ├── tools.py          # Strands ツール
│   │   ├── agent.py          # Agent 定義 + ストリーミング（consult_stream）
│   │   └── api.py            # FastAPI（/consult, /consult/stream, /health）
│   └── tests/
└── web/                      # フェーズ3
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx           # ストリーミング駆動の状態管理・結線
        ├── api.ts            # 型 + consult / consultStream(SSE)
        ├── App.css
        └── components/
            ├── ConsultForm.tsx
            ├── Loading.tsx
            ├── ResultView.tsx
            ├── CandidateCard.tsx
            ├── ConfidenceBadge.tsx
            ├── AgentTrace.tsx      # 思考/ツール/SPARQL/グラフのタイムライン
            ├── GraphView.tsx       # SVG ナレッジグラフ
            └── StreamingAnswer.tsx # 本文トークン
```

> ルートには起動スクリプト `run.sh`（agent + web 一括起動）と `README.md` を置く。

## 8. 非機能・制約

- 本システムは**情報提供ツール**であり、弁護士による法的助言の代替ではない。全回答に免責を付す。
- オントロジーは一次情報（e-Gov 法令データ）に基づき、条文原文を保持する。
- 法改正（拘禁刑への一本化等）に追従できるようデータとロジックを分離する。
- オフライン（ネット接続なし）でもオントロジー検索は動作。LLM 呼び出しのみ Bedrock 接続要。

## 9. 免責事項（UI/API 双方で明示）

> 本システムは日本の刑法に関する一般的な情報提供を目的としたものであり、個別事案に対する
> 法的助言ではありません。実際の法的対応については弁護士等の専門家にご相談ください。
