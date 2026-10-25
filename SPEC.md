# SPEC.md — 刑法オントロジー法律相談エージェント

仕様のみを記す。経緯・理由は [PLAN.md](./PLAN.md)、使い方・環境変数は [README.md](./README.md)。
コードを読めば分かる実装詳細（関数本体・ファイル構成・CSS 値など）は書かない。

## 1. 概要

相談文（日常語）を入力として、該当しうる日本の刑法上の罪を返す。返す内容:
- 該当しうる罪名・条文番号
- 構成要件の充足状況（満たしうる / 不足）
- 法定刑
- 「刑法上は該当なし」の判定とその理由

刑事のみを扱う。民事（損害賠償・慰謝料・貸金返還等）は対象外。

## 2. スコープ

### 対象
- 刑法（明治40年法律第45号）第2編「罪」（77条〜264条）で、罪を定める条のすべて
  - 個人的法益 / 社会的法益 / 国家的法益の全カテゴリ
  - 刑を他の罪に委ねる条（「強盗として論ずる」「重い刑により処断する」など）も罪として収録する
  - 罪として収録しない条: 未遂罪、親告罪、刑の減免（自首・自白・解放）、特例、準用、没収、削除条
- 相談文 → 概念 → 罪候補 → 構成要件の突合 → 回答

### 非対象
- 民事
- 特別刑法（軽犯罪法・行政刑罰法規等）
- 刑法総則（未遂・共犯・正当防衛等）の独立収録
- 量刑予測・判例検索
- 確定的な法的判断

## 3. 構成

4 層。上から順に呼び出す。
- Web UI（TypeScript + React / Vite）
- Agent API（Python / uv / FastAPI + Strands Agents SDK + Bedrock Claude Haiku 5.5）
- セマンティックレイヤー（日常語 ⇄ 法律概念）
- オントロジー層（RDF / RDFS / OWL + SPARQL + 推論）

## 4. オントロジー

### 4.1 表現形式
- RDF + RDFS + OWL（rdflib）。推論は owlrl（OWL-RL / RDFS クロージャ）を、グラフをロードした後に適用する
- データの元は YAML（人間が編集）。ビルド時に Turtle へ変換する。RDFS/OWL スキーマは YAML とは別に固定の Turtle で持つ
- 名前空間: `https://example.org/criminal-law#`（`cl:`）。ほかに `rdf:` `rdfs:` `owl:` `skos:` `xsd:` を使う
- OWL で使う制約: `owl:inverseOf`（`definedIn` ⇔ `defines`）、`owl:TransitiveProperty`（`broaderConcept`）、`owl:disjointWith`（法益カテゴリ同士の排他）
- 罪インスタンスには最下層のカテゴリ型だけを書く。上位カテゴリ型は推論で導く

### 4.2 クラス階層

```
Entity
├── Crime（罪）
│   ├── CrimeAgainstPerson（個人的法益）
│   │   ├── CrimeAgainstLifeBody（生命・身体）
│   │   ├── CrimeAgainstFreedomHonor（自由・名誉・秘密）
│   │   └── CrimeAgainstProperty（財産）
│   ├── CrimeAgainstSociety（社会的法益）
│   │   ├── CrimeAgainstPublicSafety（公共の安全）
│   │   ├── CrimeAgainstPublicTrust（公共の信用）
│   │   └── CrimeAgainstPublicMorals（風俗・健康）
│   └── CrimeAgainstState（国家的法益）
│       ├── CrimeAgainstStateExistence（国家存立）
│       └── CrimeAgainstStateFunction（国家作用）
├── Element（構成要件要素）: Conduct / Result / Object / Circumstance / Intent
├── Penalty（法定刑）: DeathPenalty / Imprisonment / Fine
├── LegalInterest（保護法益）
└── Article（条文）
```

8 つの最下層カテゴリのすべてに、1 罪以上を収録する。

章 → 最下層カテゴリの割り当て:
- 国家存立: 第2〜4章
- 国家作用: 第5〜7・20・21・25章
- 公共の安全: 第8〜11章
- 公共の信用: 第16〜19章の2
- 風俗・健康: 第14・15・23・24章、第22章のうち 174・175・183・184条
- 自由・名誉・秘密: 第12・13・31〜35章、第22章のうち 176〜182条
- 生命・身体: 第26〜30章
- 財産: 第36〜40章

### 4.3 プロパティ

| プロパティ | 定義域 → 値域 | 意味 |
|---|---|---|
| `definedIn` | Crime → Article | 規定条文 |
| `hasElement` | Crime → Element | 構成要件要素 |
| `hasPenalty` | Crime → Penalty | 法定刑 |
| `protectsLegalInterest` | Crime → LegalInterest | 保護法益 |
| `relatedTo` | Crime → Crime | 関連罪（択一・加重等） |
| `hasKeyword` | Element → Literal | 自然文マッチ用キーワード |
| `hasConcept` | Element → Concept | セマンティックレイヤー概念への参照 |

### 4.4 罪データの必須項目
- 収録の単位は 1 条 = 1 罪（「条の2」等も別の条）。1 条に複数の罪がある場合は、構成要件要素で各項を表す
- 条番号の表記は `163の2` 形式
- id / 罪名 / 条番号 / 最下層カテゴリ / 保護法益
- 構成要件要素（種別・説明・キーワード）
- 法定刑（種別 death | imprisonment | fine、下限、上限（上限なしは null）、単位 month | year | yen、原文表記）。1 罪につき 1 件以上
- 条文原文。1 罪につき必須。条の全項を含む
- 法定刑は拘禁刑への一本化（2025年6月施行）を反映する。条文は e-Gov などの一次情報から転記する
- 刑を他の罪に委ねる条の法定刑は、委ねた先の刑を記し、原文表記（例: 「強盗として論ずる」）を残す
- 併科の区別（「及び」= 必ず併科、「若しくは / 又は」= 選択、「又はこれを併科する」= 任意的併科）は原文表記で示す
- 刑種に無い拘留は、罰金の原文表記に含める（例: 「30万円以下の罰金又は拘留若しくは科料」）

### 4.5 セマンティックレイヤー
- 概念は `skos:Concept` として表す。各概念が持つ項目:
  - 正式名（prefLabel）
  - 表層語（altLabel。日常語の言い換え）
  - 上位概念（推移的にたどれる。循環は禁止）
  - 指す罪（`indicatesCrime`）。1 概念が複数の罪を指してよい
- 照合: 相談文に表層語が文字列として含まれるか（部分一致）で判定する
  - 照合の前に、相談文と表層語の両方を正規化する（空白・記号の除去、英字の小文字化）
  - 根拠語（matched_surface）として返すのは、相談文の原文の該当部分（正規化前の表記）。同じ語が複数回現れた場合は、最初の出現を返す
- 概念のスコア: マッチした表層語 1 つごとに `1.0 + 文字数 × 0.1` を加算する
- 罪候補: 概念が指す罪を集める。同じ罪を指す概念が複数あれば、スコアを合算して 1 件にまとめる。スコアの高い順に並べる
- 概念・表層語が指す罪 ID は、すべて収録済みの罪でなければならない
- すべての罪は、1 つ以上の概念から指されなければならない
- 表層語は 2 文字以上

## 5. エージェント

### 5.1 モデル・実行環境
- Amazon Bedrock Claude Haiku 5.5。既定の推論プロファイル ID は `global.anthropic.claude-haiku-5-5`。環境変数で上書きできる
- 認証・リージョン・モデル ID はリポジトリに固定せず、実行環境から与える
- `temperature` は指定しない（モデルが受け付けない）
- エンドポイント: `POST /consult`、`POST /consult/stream`、`GET /health`

### 5.2 ツール
単一エージェント + 3 ツール。

- `search_crimes_by_text(consultation)` → 罪候補のリスト。該当なしは空リスト
  - 各候補の項目: crime_id / 罪名 / 条番号 / カテゴリ / 法定刑の概要 / score / via_concepts（経由した概念 ID）/ matched_surface（相談文中でマッチした語。原文表記・重複なし）
- `get_crime_detail(crime_id)` → 条文原文・構成要件・法定刑・保護法益・関連罪。未知の ID のときはエラーを返す
  - 関連罪（related_to）の各項目: crime_id / 罪名 / 条番号。罪名・条番号はオントロジーの値を付けて返す（LLM に記憶で補わせない）
- `list_crime_categories()` → カテゴリ一覧。各カテゴリの項目:
  - count: 推論込みの所属罪数
  - direct_count: 直接そのカテゴリに収録した罪数
  - leaf: 最下層かどうか

概念だけを返すツール（相談文 → 概念）はエージェントに提供しない。概念の解決結果はオントロジー層の API として可視化に使う。

### 5.3 システムプロンプト（要旨）
- 役割: 刑法に関する情報提供。確定的な法的助言は行わない。断定を避け「該当しうる」と表現する
- 手順:
  1. 相談文から事実関係を把握する
  2. `search_crimes_by_text` で候補を得る。各候補の matched_surface を理由説明の根拠に使う
  3. 候補ごとに `get_crime_detail` で構成要件を確認する
  4. 構成要件の充足（matched）/ 不足（missing）を評価する
  5. 該当しうる罪があれば条文・法定刑・理由を示す。候補が無い、または民事のみの問題なら no_crime=true とする
     - このとき summary に、刑法上は該当しないと考えられる理由と、事情によっては該当しうる場合（例: 最初から返すつもりがなく借りたなら詐欺罪）を平易に書く
- 出力はすべて日本語。confidence は構成要件の充足度から high / medium / low を付ける
- 禁止事項
  - 免責文・注意書き（「本回答は一般的な情報提供であり…」等）を書かない
  - ツール結果（`search_crimes_by_text` / `get_crime_detail`）で確認できない罪に触れない。no_crime の「事情によっては該当しうる場合」で罪を挙げるときも、仮定の事実で `search_crimes_by_text` を呼び、得た候補から挙げる。候補が得られなかった罪は、断り書きを付けても挙げない

### 5.4 構造化出力

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
  "no_crime": false
}
```

免責事項のフィールドは持たない。no_crime=true のときの理由は、専用のフィールドを設けず summary に書く。

### 5.5 ストリーミング（SSE）
`POST /consult/stream` は `/consult` と同じ body を受け取り、`data: <JSON>\n\n` 形式で次のイベントを順に配信する。

| type | 内容 |
|---|---|
| `start` / `done` / `error` | 開始 / 完了 / エラー（`message`） |
| `reasoning` | モデルの思考の断片 |
| `token` | 回答本文の断片 |
| `tool_use` | ツール呼び出し（`name`, `input`） |
| `sparql` | ツール呼び出しに対応する SPARQL（`label`, `sparql`） |
| `graph` | 対応するサブグラフ（`crime_id`, `triples`, `turtle`） |
| `tool_result` | ツール結果の要約（`status`, `summary`） |
| `result` | §5.4 の構造化結果 |

- `sparql` / `graph` を出すのは `search_crimes_by_text` と `get_crime_detail` の呼び出し時だけ
- LLM に渡すツール出力とは別に、ストリーム側で付けて配信する
- 可視化に失敗しても、回答の処理は止めない

## 6. Web UI

### 6.1 技術
- TypeScript + React（Vite）。スタイルはプレーン CSS で、外部 UI ライブラリは使わない
- `/consult/stream` を既定で購読する

### 6.2 画面構成（単一ページ・縦フロー）
- ① 事件の入力: 相談文、例チップ、「判定を開始する」ボタン
- ② 判定ライブビュー（ストリーミング中に出る）
  - 4 段のステップインジケータ。受信したイベントで点灯する
    - 事実の把握: start / 最初の reasoning
    - 候補の抽出: search の tool_use / sparql / graph
    - 構成要件の照合: detail の tool_use / graph / reasoning
    - 判定: result
  - 思考・ツール・SPARQL・ナレッジグラフ（ノード・エッジ図 + トリプル一覧）・本文ストリーム
- ③ 判定結果
  - 判定ヘッダー: 候補ありなら「犯罪が成立しうる」と候補件数、no_crime なら「罪に問うは難し」
  - 事件の要約
  - 罪ごとのカード
    - 罪名・条番号
    - 確信度メーター
    - 充足ゲージ（matched 件数 / (matched + missing) 件数）
    - ✓ 満たしうる行 / ？ 要確認・不足 行
    - 「成立した場合の刑」
    - 「判定の根拠」
  - カードをクリックすると、②の対応するグラフ / SPARQL へスクロールする（crime_id で対応づける）
- 画面末尾に「出力結果の利用は自己責任でお願いします。」

### 6.3 表示情報の不変条件
UI が表示するのは API が返す情報だけ。新しい分析・スコア・事実は足さない。判定ヘッダー・メーター・ゲージ・ステップは、既存の値（no_crime / candidates 数 / confidence / matched / missing / イベント種別）から導くだけにする。

| 情報要素 | 置き場所 |
|---|---|
| 相談テキスト・例チップ | ① |
| summary | ③ 事件の要約 |
| crime_label / article | ③ カード見出し |
| confidence | ③ 確信度メーター（同値） |
| matched_elements / missing_elements | ③ 充足ゲージ + ✓ / ？行 |
| penalty_text | ③「成立した場合の刑」 |
| reasoning | ③「判定の根拠」 |
| no_crime | ③ 判定ヘッダー + 説明 |
| reasoning / tool_use / tool_result / sparql（stream） | ② |
| graph（stream） | ② ナレッジグラフ |
| token（stream） | ② 判定文の生成 |

### 6.4 視覚デザイン（法廷テーマ）
- 配色: 羊皮紙調の地、紺（威厳）、ゴールド（格式）。成立しうる = 深紅系、該当なし = 紺系
- 見出し（H1・ステージ見出し・罪名・判定文言）は明朝体、本文はゴシック体
- ヘッダー: 紺地 + ゴールドの下罫 + 天秤のクレスト。タイトルは「刑法あてはめ判定」（「判定」をゴールドで強調）
- ファビコン: 天秤。ページタイトルは「刑法あてはめ判定 ⚖」
- アニメーション: `prefers-reduced-motion` を尊重し、無効のときは即時に表示する
- アクセシビリティ: メーター・ゲージに `role="meter"` と aria 属性を付ける。キーボードとスクリーンリーダーで判定結果を読めるようにする

## 7. 非機能・制約
- 情報提供ツールであり、弁護士の法的助言の代替ではない
- 条文原文は一次情報（e-Gov 法令データ）を保持する
- 法改正に追従できるよう、データとロジックを分離する
- オントロジー検索はオフラインで動く。ネット接続が要るのは LLM 呼び出し（Bedrock）だけ
  - 例外: 条文の照合スクリプト（e-Gov と statute_text の差分を出す）は手動実行の開発ツールで、ネット接続を要する。テスト・ビルドからは呼ばない
