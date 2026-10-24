// 刑法相談エージェント API クライアント（型付き）。
// レスポンス型は agent 側 ConsultationResult (SPEC §5.4) に一致させる。

export type Confidence = "high" | "medium" | "low";

export interface CrimeCandidate {
  crime_label: string;
  article: string;
  confidence: Confidence | string;
  matched_elements: string[];
  missing_elements: string[];
  penalty_text: string;
  reasoning: string;
}

export interface ConsultationResult {
  summary: string;
  candidates: CrimeCandidate[];
  no_crime: boolean;
}

// API ベース URL（環境変数 VITE_API_BASE で上書き可）
const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8099";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** POST /consult に相談文を送り、構造化回答を取得する。 */
export async function consult(text: string, signal?: AbortSignal): Promise<ConsultationResult> {
  const resp = await fetch(`${API_BASE}/consult`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // JSON でない場合はステータスのみ
    }
    throw new ApiError(resp.status, detail);
  }

  return (await resp.json()) as ConsultationResult;
}

// ------------------------------------------------------------------
// ストリーミング（SSE）: 思考回路・ツール呼び出し・SPARQL・グラフ・本文
// ------------------------------------------------------------------

export interface Triple {
  s: string;
  p: string;
  o: string;
}

/** agent.consult_stream が流すイベント（type で判別）。 */
export type StreamEvent =
  | { type: "start" }
  | { type: "reasoning"; text: string }
  | { type: "token"; text: string }
  | { type: "tool_use"; name: string; input: Record<string, unknown> }
  | { type: "sparql"; label: string; sparql: string }
  | { type: "graph"; crime_id: string; sparql: string; triples: Triple[]; turtle: string }
  | { type: "tool_result"; status: string; summary: string }
  | { type: "result"; result: ConsultationResult }
  | { type: "done" }
  | { type: "error"; message: string };

/**
 * POST /consult/stream に接続し、SSE イベントを逐次コールバックへ渡す。
 * EventSource は POST 不可のため fetch + ReadableStream で実装する。
 */
export async function consultStream(
  text: string,
  onEvent: (ev: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/consult/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!resp.ok || !resp.body) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(resp.status, detail);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (chunk: string) => {
    // SSE はイベント間を空行（\n\n）で区切る
    buffer += chunk;
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of raw.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const json = trimmed.slice(5).trim();
        if (!json) continue;
        try {
          onEvent(JSON.parse(json) as StreamEvent);
        } catch {
          // パース不能な行は無視
        }
      }
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    flush(decoder.decode(value, { stream: true }));
  }
  // 残余
  if (buffer.trim()) flush("\n\n");
}
