import { useState } from "react";
import type { StreamEvent, Triple } from "../api";
import { GraphView } from "./GraphView";

// 判定ライブビューの進行ログ（SPEC §6.2 / §6.3）。
// 表示するイベントは従来と同一（reasoning/tool_use/sparql/graph/tool_result）。
// ラベル文言のみ「判定の文脈」に変更する。GraphView の描画ロジックは不変。

// タイムラインに表示する種別のイベント（token/result/done/start は除外）
type TraceItem =
  | { type: "reasoning"; text: string }
  | { type: "tool_use"; name: string; input: Record<string, unknown> }
  | { type: "sparql"; label: string; sparql: string }
  | { type: "graph"; crime_id: string; sparql: string; triples: Triple[]; turtle: string }
  | { type: "tool_result"; status: string; summary: string };

export function isTraceItem(ev: StreamEvent): ev is TraceItem {
  return (
    ev.type === "reasoning" ||
    ev.type === "tool_use" ||
    ev.type === "sparql" ||
    ev.type === "graph" ||
    ev.type === "tool_result"
  );
}

// 対応グラフへスクロールするための DOM id（crime_id で対応づけ）
export function graphAnchorId(crimeId: string): string {
  return `graph-${crimeId}`;
}

function Collapsible({
  title,
  children,
  defaultOpen = false,
}: {
  title: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="collapsible">
      <button className="collapsible-head" onClick={() => setOpen((v) => !v)}>
        <span className={`chevron ${open ? "open" : ""}`}>▶</span>
        {title}
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </div>
  );
}

function TripleTable({ triples }: { triples: Triple[] }) {
  return (
    <table className="triple-table">
      <thead>
        <tr>
          <th>主語 (S)</th>
          <th>述語 (P)</th>
          <th>目的語 (O)</th>
        </tr>
      </thead>
      <tbody>
        {triples.map((t, i) => (
          <tr key={i}>
            <td>{t.s}</td>
            <td>{t.p}</td>
            <td>{t.o}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TraceEntry({ item }: { item: TraceItem }) {
  switch (item.type) {
    case "reasoning":
      return (
        <div className="trace-entry trace-reasoning">
          <span className="trace-icon">🧠</span>
          <div className="trace-content">
            <span className="trace-label">検討メモ</span>
            <p className="reasoning-text">{item.text}</p>
          </div>
        </div>
      );
    case "tool_use":
      return (
        <div className="trace-entry trace-tool">
          <span className="trace-icon">🔧</span>
          <div className="trace-content">
            <span className="trace-label">参照アクション: {item.name}</span>
            <code className="trace-code">{JSON.stringify(item.input, null, 0)}</code>
          </div>
        </div>
      );
    case "tool_result":
      return (
        <div className="trace-entry trace-result-ev">
          <span className="trace-icon">📥</span>
          <div className="trace-content">
            <span className="trace-label">参照結果 ({item.status})</span>
            <code className="trace-code">{item.summary}</code>
          </div>
        </div>
      );
    case "sparql":
      return (
        <div className="trace-entry trace-sparql">
          <span className="trace-icon">🔎</span>
          <div className="trace-content">
            <Collapsible title={<span className="trace-label">参照クエリ (SPARQL): {item.label}</span>}>
              <pre className="sparql-block">{item.sparql}</pre>
            </Collapsible>
          </div>
        </div>
      );
    case "graph":
      return (
        <div
          className="trace-entry trace-graph"
          id={graphAnchorId(item.crime_id)}
          tabIndex={-1}
        >
          <span className="trace-icon">🕸️</span>
          <div className="trace-content">
            <Collapsible
              title={
                <span className="trace-label">
                  ナレッジグラフ: {item.crime_id}（{item.triples.length} トリプル）
                </span>
              }
              defaultOpen
            >
              <GraphView crimeId={item.crime_id} triples={item.triples} />
              <Collapsible title={<span className="subtle">トリプル一覧（表）</span>}>
                <TripleTable triples={item.triples} />
              </Collapsible>
            </Collapsible>
          </div>
        </div>
      );
  }
}

export function AgentTrace({ items }: { items: TraceItem[] }) {
  if (items.length === 0) return null;
  return (
    <section className="agent-trace">
      <Collapsible
        title={<strong>判定の進行（{items.length} ステップ）</strong>}
        defaultOpen
      >
        <div className="trace-timeline">
          {items.map((item, i) => (
            <TraceEntry key={i} item={item} />
          ))}
        </div>
      </Collapsible>
    </section>
  );
}

export type { TraceItem };
