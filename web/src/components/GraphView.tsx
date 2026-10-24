import { useMemo, useState } from "react";
import type { Triple } from "../api";

// ---- グラフモデル構築 ---------------------------------------------

type NodeKind =
  | "crime"
  | "article"
  | "element"
  | "penalty"
  | "interest"
  | "concept"
  | "related"
  | "class";

interface GNode {
  id: string; // トリプル中のローカル識別子（cl:xxx 等）
  label: string; // 表示名
  kind: NodeKind;
  sub?: string[]; // 付随情報（キーワード・刑種など）
}

interface GEdge {
  from: string;
  to: string;
  label: string; // 述語（短縮名の末尾）
}

// 述語ローカル名
function predName(p: string): string {
  return p.replace(/^.*[:#]/, "");
}

// リテラルか URI(cl:/skos:/rdf:/rdfs:) か
function isRef(term: string): boolean {
  return /^(cl|skos|rdf|rdfs):/.test(term);
}

interface GraphModel {
  nodes: GNode[];
  edges: GEdge[];
  centerId: string | null;
}

// 構造を表す述語のみエッジにする。リテラル系はノード属性へ畳み込む。
const STRUCT_PREDS = new Set([
  "definedIn",
  "hasElement",
  "hasPenalty",
  "protectsLegalInterest",
  "relatedTo",
  "indicatesCrime",
]);

const LABEL_PREDS = new Set(["label", "prefLabel", "statuteText", "note"]);

function buildGraph(crimeId: string, triples: Triple[]): GraphModel {
  const centerId = `cl:${crimeId}`;
  const nodes = new Map<string, GNode>();
  const edges: GEdge[] = [];
  const edgeSeen = new Set<string>();

  const ensure = (id: string, kind: NodeKind): GNode => {
    let n = nodes.get(id);
    if (!n) {
      n = { id, label: id.replace(/^.*[:#]/, ""), kind, sub: [] };
      nodes.set(id, n);
    }
    return n;
  };

  // 中心ノード
  ensure(centerId, "crime");

  // 種別推定用マップ
  const kindOf = (id: string): NodeKind => {
    if (id === centerId) return "crime";
    if (/^cl:art/.test(id)) return "article";
    if (/-el\d+$/.test(id)) return "element";
    if (/-pen\d+$/.test(id)) return "penalty";
    if (/^cl:concept-/.test(id)) return "concept";
    return "class";
  };

  for (const t of triples) {
    const p = predName(t.p);

    // ラベル系リテラル → ノードの表示名
    if (LABEL_PREDS.has(p) && isRef(t.s) && !isRef(t.o)) {
      const n = ensure(t.s, kindOf(t.s));
      if (p === "label" || p === "prefLabel") {
        n.label = t.o;
      } else if (p === "note") {
        n.sub?.push(t.o);
      } else if (p === "statuteText") {
        n.sub?.push(t.o);
      }
      continue;
    }

    // 構造エッジ
    if (STRUCT_PREDS.has(p) && isRef(t.s) && isRef(t.o)) {
      let toKind: NodeKind = kindOf(t.o);
      let fromId = t.s;
      let toId = t.o;
      if (p === "protectsLegalInterest") continue; // リテラルのことが多い
      if (p === "relatedTo") toKind = "related";
      if (p === "indicatesCrime") {
        // concept → crime の向き。中心へ入るエッジとして扱う
        fromId = t.s;
        toId = t.o;
        ensure(fromId, "concept");
      }
      ensure(fromId, kindOf(fromId));
      ensure(toId, toKind);
      const key = `${fromId}|${p}|${toId}`;
      if (!edgeSeen.has(key)) {
        edgeSeen.add(key);
        edges.push({ from: fromId, to: toId, label: p });
      }
      continue;
    }

    // 保護法益（リテラル）→ 専用ノード化
    if (p === "protectsLegalInterest" && !isRef(t.o)) {
      const id = `interest:${t.o}`;
      const n = ensure(id, "interest");
      n.label = t.o;
      edges.push({ from: t.s, to: id, label: "protectsLegalInterest" });
      continue;
    }

    // 要素の属性（keyword/elementType）→ ノードの sub へ
    if ((p === "hasKeyword" || p === "elementType") && isRef(t.s) && !isRef(t.o)) {
      const n = ensure(t.s, kindOf(t.s));
      if (p === "elementType") n.label = `[${t.o}] ${n.label}`;
      else n.sub?.push(t.o);
      continue;
    }

    // 刑の属性（penaltyType/unit/maxValue/minValue）→ sub へ
    if (
      ["penaltyType", "unit", "maxValue", "minValue", "articleNumber"].includes(p) &&
      isRef(t.s) &&
      !isRef(t.o)
    ) {
      const n = ensure(t.s, kindOf(t.s));
      n.sub?.push(`${p}=${t.o}`);
      continue;
    }
    // rdf:type / defines などは図では省略（ノイズ低減）
  }

  return { nodes: Array.from(nodes.values()), edges, centerId };
}

// ---- レイアウト（放射状） -----------------------------------------

interface Placed extends GNode {
  x: number;
  y: number;
}

const KIND_COLOR: Record<NodeKind, string> = {
  crime: "#dc2626",
  article: "#2563eb",
  element: "#16a34a",
  penalty: "#d97706",
  interest: "#0891b2",
  concept: "#8b5cf6",
  related: "#db2777",
  class: "#6b7280",
};

const KIND_LABEL: Record<NodeKind, string> = {
  crime: "罪",
  article: "条文",
  element: "構成要件",
  penalty: "法定刑",
  interest: "保護法益",
  concept: "概念",
  related: "関連罪",
  class: "クラス",
};

function layout(model: GraphModel, width: number, height: number): Placed[] {
  const cx = width / 2;
  const cy = height / 2;
  const placed: Placed[] = [];

  const center = model.nodes.find((n) => n.id === model.centerId);
  const others = model.nodes.filter((n) => n.id !== model.centerId);

  if (center) placed.push({ ...center, x: cx, y: cy });

  // 中心に直接つながるノードを第1リング、それ以外を第2リングへ
  const neighbors = new Set<string>();
  for (const e of model.edges) {
    if (e.from === model.centerId) neighbors.add(e.to);
    if (e.to === model.centerId) neighbors.add(e.from);
  }

  const ring1 = others.filter((n) => neighbors.has(n.id));
  const ring2 = others.filter((n) => !neighbors.has(n.id));

  const place = (list: GNode[], radius: number, phase: number) => {
    const n = list.length;
    list.forEach((node, i) => {
      const angle = phase + (2 * Math.PI * i) / Math.max(n, 1);
      placed.push({
        ...node,
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      });
    });
  };

  const r1 = Math.min(width, height) * 0.28;
  const r2 = Math.min(width, height) * 0.45;
  place(ring1, r1, -Math.PI / 2);
  place(ring2, r2, -Math.PI / 2 + 0.4);

  return placed;
}

// ---- 描画 ---------------------------------------------------------

export function GraphView({ crimeId, triples }: { crimeId: string; triples: Triple[] }) {
  const [hover, setHover] = useState<Placed | null>(null);
  const width = 640;
  const height = 420;

  const { placed, edges } = useMemo(() => {
    const model = buildGraph(crimeId, triples);
    const placedNodes = layout(model, width, height);
    return { placed: placedNodes, edges: model.edges };
  }, [crimeId, triples]);

  const posOf = useMemo(() => {
    const m = new Map<string, Placed>();
    for (const p of placed) m.set(p.id, p);
    return m;
  }, [placed]);

  const usedKinds = Array.from(new Set(placed.map((p) => p.kind)));

  return (
    <div className="graph-view">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="graph-svg"
        role="img"
        aria-label={`${crimeId} のナレッジグラフ`}
      >
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#9ca3af" />
          </marker>
        </defs>

        {/* エッジ */}
        {edges.map((e, i) => {
          const a = posOf.get(e.from);
          const b = posOf.get(e.to);
          if (!a || !b) return null;
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={i} className="graph-edge">
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="#cbd5e1"
                strokeWidth={1.3}
                markerEnd="url(#arrow)"
              />
              <text x={mx} y={my - 2} className="edge-label">
                {e.label}
              </text>
            </g>
          );
        })}

        {/* ノード */}
        {placed.map((n) => {
          const r = n.kind === "crime" ? 30 : 20;
          const color = KIND_COLOR[n.kind];
          return (
            <g
              key={n.id}
              className="graph-node"
              transform={`translate(${n.x},${n.y})`}
              onMouseEnter={() => setHover(n)}
              onMouseLeave={() => setHover(null)}
            >
              <circle r={r} fill={color} fillOpacity={0.15} stroke={color} strokeWidth={2} />
              <text className="node-label" y={r + 13} textAnchor="middle">
                {n.label.length > 14 ? n.label.slice(0, 13) + "…" : n.label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* 凡例 */}
      <div className="graph-legend">
        {usedKinds.map((k) => (
          <span key={k} className="legend-item">
            <span className="legend-dot" style={{ background: KIND_COLOR[k] }} />
            {KIND_LABEL[k]}
          </span>
        ))}
      </div>

      {/* ホバー詳細 */}
      {hover && (hover.sub?.length ?? 0) > 0 && (
        <div className="graph-tooltip">
          <strong>{hover.label}</strong>
          <ul>
            {hover.sub!.slice(0, 12).map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
