"""e-Gov 法令 API から刑法の条文を取得し、crimes.yaml の statute_text と照合する。

手動実行の開発ツール（ネット接続が要る）。テスト・ビルドからは呼ばない。

使い方（ontology/ で実行）:
    uv run python scripts/egov_statutes.py check          # 差分を表示（差分があれば終了コード 1）
    uv run python scripts/egov_statutes.py check --fix    # 差分のある statute_text を e-Gov の原文で書き換える
    uv run python scripts/egov_statutes.py show 96の2 238  # 指定条の原文を YAML の値として出力
    uv run python scripts/egov_statutes.py list           # 第2編の条一覧（章・見出し・収録済みか）

共通オプション:
    --xml PATH  取得済みの XML を使う（ネット接続なしで再実行するとき）

条文のテキスト化の規則:
    - 項ごとに改行。第2項以降は項番号（「２」等）+ 全角空白を前置する
    - 号・号の細分（イ・ロ等）は改行し、号名 + 全角空白を前置する
    - 同じ項・号の中の複数の文（本文・ただし書等）は連結する
    - ルビ（Rt）は除く
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

LAW_ID = "140AC0000000045"  # 刑法（明治40年法律第45号）
API_URL = f"https://laws.e-gov.go.jp/api/1/lawdata/{LAW_ID}"
CRIMES_YAML = Path(__file__).resolve().parents[1] / "data" / "crimes.yaml"

# 号の細分のタグ（Subitem1 ... Subitem10）
_SUBITEM_RE = re.compile(r"^Subitem(\d+)$")


# ---------------------------------------------------------------------------
# XML 取得・テキスト化
# ---------------------------------------------------------------------------
def fetch_xml(xml_path: str | None) -> ET.Element:
    if xml_path:
        data = Path(xml_path).read_bytes()
    else:
        with urllib.request.urlopen(API_URL, timeout=60) as resp:  # noqa: S310 (固定 URL)
            data = resp.read()
    root = ET.fromstring(data)
    code = root.findtext(".//Result/Code")
    if code != "0":
        raise SystemExit(f"e-Gov API error: code={code} {root.findtext('.//Result/Message')}")
    return root


def _text(el: ET.Element) -> str:
    """要素内のテキストを連結する（ルビの読み Rt は除く）。"""
    parts: list[str] = []

    def walk(e: ET.Element) -> None:
        if e.tag == "Rt":
            return
        if e.text:
            parts.append(e.text)
        for c in e:
            walk(c)
            if c.tail:
                parts.append(c.tail)

    walk(el)
    return "".join(parts).strip()


def _sentences(container: ET.Element | None) -> str:
    """ParagraphSentence / ItemSentence 等の文を連結する。Column は全角空白で区切る。"""
    if container is None:
        return ""
    columns = container.findall("Column")
    if columns:
        return "　".join(
            "".join(_text(s) for s in col.findall("Sentence")) for col in columns
        )
    return "".join(_text(s) for s in container.findall("Sentence"))


def _render_items(parent: ET.Element, lines: list[str]) -> None:
    """号（Item）・号の細分（SubitemN）を 1 行ずつ追加する。"""
    for child in parent:
        if child.tag == "Item":
            title, sent = "ItemTitle", "ItemSentence"
        elif m := _SUBITEM_RE.match(child.tag):
            title, sent = f"Subitem{m.group(1)}Title", f"Subitem{m.group(1)}Sentence"
        else:
            continue
        head = _text(child.find(title)) if child.find(title) is not None else ""
        lines.append(f"{head}　{_sentences(child.find(sent))}".strip())
        _render_items(child, lines)


def render_article(article: ET.Element) -> str:
    lines: list[str] = []
    for i, para in enumerate(article.findall("Paragraph")):
        body = _sentences(para.find("ParagraphSentence"))
        num = _text(para.find("ParagraphNum")) if para.find("ParagraphNum") is not None else ""
        lines.append(f"{num}　{body}" if i > 0 and num else body)
        _render_items(para, lines)
    return "\n".join(lines)


def part2_articles(root: ET.Element) -> list[dict]:
    """第2編の条を章順に返す。"""
    main = root.find(".//MainProvision")
    part2 = next(p for p in main.iter("Part") if p.get("Num") == "2")
    out: list[dict] = []
    for ch in part2.findall("Chapter"):
        ch_title = _text(ch.find("ChapterTitle"))
        for a in ch.iter("Article"):
            out.append(
                {
                    "num": a.get("Num"),  # 例: "96_2"、削除条の範囲は "73:76"
                    "chapter": ch.get("Num"),
                    "chapter_title": ch_title,
                    "caption": _text(a.find("ArticleCaption")) if a.find("ArticleCaption") is not None else "",
                    "text": render_article(a),
                }
            )
    return out


def to_yaml_num(num: str) -> str:
    """XML の条番号（96_2）→ crimes.yaml の表記（96の2）。"""
    return num.replace("_", "の")


# ---------------------------------------------------------------------------
# crimes.yaml
# ---------------------------------------------------------------------------
def load_crimes() -> list[dict]:
    with CRIMES_YAML.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["crimes"]


def rewrite_statute_texts(fixes: dict[str, str]) -> int:
    """crimes.yaml の statute_text 行を、id ごとに置き換える（コメント・書式は保つ）。

    statute_text は 1 行の値である前提。値は JSON 文字列（YAML のダブルクォート文字列と互換）で書く。
    """
    lines = CRIMES_YAML.read_text(encoding="utf-8").splitlines(keepends=True)
    current_id: str | None = None
    changed = 0
    id_re = re.compile(r"^\s*-\s+id:\s*(\S+)\s*$")
    st_re = re.compile(r"^(\s*)statute_text:\s")
    for i, line in enumerate(lines):
        if m := id_re.match(line):
            current_id = m.group(1)
        elif (m := st_re.match(line)) and current_id in fixes:
            lines[i] = f"{m.group(1)}statute_text: {json.dumps(fixes[current_id], ensure_ascii=False)}\n"
            changed += 1
            current_id = None
    CRIMES_YAML.write_text("".join(lines), encoding="utf-8")
    return changed


# ---------------------------------------------------------------------------
# サブコマンド
# ---------------------------------------------------------------------------
def cmd_check(root: ET.Element, fix: bool) -> int:
    egov = {to_yaml_num(a["num"]): a for a in part2_articles(root)}
    fixes: dict[str, str] = {}
    missing: list[str] = []
    for c in load_crimes():
        a = egov.get(c["article"])
        if a is None:
            missing.append(f"{c['id']} ({c['article']}条)")
            continue
        if c["statute_text"] != a["text"]:
            fixes[c["id"]] = a["text"]
            print(f"=== {c['id']} ({c['article']}条) ===")
            for d in difflib.unified_diff(
                c["statute_text"].splitlines(), a["text"].splitlines(),
                "crimes.yaml", "e-Gov", lineterm="", n=0,
            ):
                print(d)
    for m in missing:
        print(f"!!! e-Gov 第2編に無い条: {m}", file=sys.stderr)
    print(f"\n差分 {len(fixes)} 件 / 不明な条 {len(missing)} 件")
    if fix and fixes:
        n = rewrite_statute_texts(fixes)
        print(f"crimes.yaml の statute_text を {n} 件書き換えた")
        return 1 if missing else 0
    return 1 if fixes or missing else 0


def cmd_show(root: ET.Element, nums: list[str]) -> int:
    egov = {to_yaml_num(a["num"]): a for a in part2_articles(root)}
    rc = 0
    for n in nums:
        a = egov.get(n)
        if a is None:
            print(f"# {n}: 第2編に無い", file=sys.stderr)
            rc = 1
            continue
        print(f"# {n}条 {a['caption']}（{a['chapter_title']}）")
        print(f"statute_text: {json.dumps(a['text'], ensure_ascii=False)}")
    return rc


def cmd_list(root: ET.Element) -> int:
    recorded = {c["article"] for c in load_crimes()}
    for a in part2_articles(root):
        n = to_yaml_num(a["num"])
        mark = "*" if n in recorded else " "
        first = a["text"].split("\n", 1)[0]
        print(f"{mark} {a['chapter']:>4} {n:<8} {a['caption']:<24} {first[:50]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml", help="取得済みの e-Gov XML を使う")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check", help="crimes.yaml と e-Gov の条文を照合する")
    p_check.add_argument("--fix", action="store_true", help="差分を e-Gov の原文で書き換える")
    p_show = sub.add_parser("show", help="指定条の原文を出力する")
    p_show.add_argument("articles", nargs="+", help="条番号（例: 96の2）")
    sub.add_parser("list", help="第2編の条一覧")
    args = ap.parse_args()

    root = fetch_xml(args.xml)
    if args.cmd == "check":
        return cmd_check(root, args.fix)
    if args.cmd == "show":
        return cmd_show(root, args.articles)
    return cmd_list(root)


if __name__ == "__main__":
    sys.exit(main())
