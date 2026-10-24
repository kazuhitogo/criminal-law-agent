import { useCallback, useMemo, useRef, useState } from "react";
import "./App.css";
import {
  consultStream,
  ApiError,
  type ConsultationResult,
  type StreamEvent,
  type Triple,
} from "./api";
import { ConsultForm } from "./components/ConsultForm";
import { Loading } from "./components/Loading";
import { ResultView } from "./components/ResultView";
import { StreamingAnswer } from "./components/StreamingAnswer";
import {
  AgentTrace,
  isTraceItem,
  graphAnchorId,
  type TraceItem,
} from "./components/AgentTrace";
import { StepIndicator, type JudgeStep } from "./components/StepIndicator";

const DISCLAIMER =
  "本システムは日本の刑法に関する一般的な情報提供を目的としたものであり、個別事案に対する法的助言ではありません。実際の法的対応については弁護士等の専門家にご相談ください。";

// prefers-reduced-motion を尊重したスクロール挙動
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
  );
}

function scrollToId(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({
    behavior: prefersReducedMotion() ? "auto" : "smooth",
    block: "start",
  });
  // 支援技術向けにフォーカス可能なら移す
  if (typeof (el as HTMLElement).focus === "function") {
    (el as HTMLElement).focus({ preventScroll: true });
  }
}

// graph イベントの triples から中心ノード（cl:{crime_id}）のラベルを取り出す。
// candidate.crime_label とのマッチに使う。新データは作らない（既存トリプル読取のみ）。
function crimeLabelFromTriples(crimeId: string, triples: Triple[]): string | null {
  const center = `cl:${crimeId}`;
  for (const t of triples) {
    const p = t.p.replace(/^.*[:#]/, "");
    if (t.s === center && (p === "label" || p === "prefLabel")) {
      return t.o;
    }
  }
  return null;
}

function App() {
  const [streaming, setStreaming] = useState(false);
  const [trace, setTrace] = useState<TraceItem[]>([]);
  const [streamText, setStreamText] = useState("");
  const [result, setResult] = useState<ConsultationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [step, setStep] = useState<JudgeStep>(0);
  // 罪名 → 対応グラフの crime_id（カード→②スクロール用）
  const [labelToCrimeId, setLabelToCrimeId] = useState<Record<string, string>>({});

  const abortRef = useRef<AbortController | null>(null);
  const liveRef = useRef<HTMLDivElement | null>(null);

  const handleEvent = useCallback((ev: StreamEvent) => {
    // --- ステップ導出（表示情報は増やさない。イベント種別の可視化のみ） ---
    switch (ev.type) {
      case "start":
        setStep((s) => (s < 1 ? 1 : s));
        break;
      case "reasoning":
        setStep((s) => (s < 1 ? 1 : s));
        break;
      case "tool_use":
        if (ev.name === "get_crime_detail") setStep((s) => (s < 3 ? 3 : s));
        else setStep((s) => (s < 2 ? 2 : s));
        break;
      case "sparql":
      case "graph":
        setStep((s) => (s < 2 ? 2 : s));
        break;
      case "result":
        setStep(4);
        break;
    }

    // --- crime_id ↔ 罪名マップ構築（graph の中心ノードラベル） ---
    if (ev.type === "graph") {
      const label = crimeLabelFromTriples(ev.crime_id, ev.triples);
      if (label) {
        setLabelToCrimeId((prev) =>
          prev[label] ? prev : { ...prev, [label]: ev.crime_id },
        );
      }
    }

    // --- トレース / 本文 / 結果 ---
    if (isTraceItem(ev)) {
      setTrace((prev) => [...prev, ev]);
      return;
    }
    switch (ev.type) {
      case "token":
        setStreamText((prev) => prev + ev.text);
        break;
      case "result":
        setResult(ev.result);
        break;
      case "error":
        setError(ev.message);
        break;
      // start / done は状態遷移のみ
    }
  }, []);

  const handleSubmit = async (text: string) => {
    // 前回分をリセット
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setStreaming(true);
    setStarted(true);
    setTrace([]);
    setStreamText("");
    setResult(null);
    setError(null);
    setStep(1);
    setLabelToCrimeId({});

    // 送信後、入力ブロックを縮小し②ライブビューへスクロール誘導
    requestAnimationFrame(() => scrollToId("judge-live"));

    try {
      await consultStream(text, handleEvent, controller.signal);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        // ユーザによる中断は無視
      } else if (e instanceof ApiError) {
        setError(`エラー (${e.status}): ${e.message}`);
      } else if (e instanceof Error) {
        setError(`通信エラー: ${e.message}`);
      } else {
        setError("不明なエラーが発生しました。");
      }
    } finally {
      setStreaming(false);
    }
  };

  // カード → ②の対応グラフへスクロール（crime_id で対応）
  const canLocate = useCallback(
    (crimeLabel: string) => Boolean(labelToCrimeId[crimeLabel]),
    [labelToCrimeId],
  );
  const onLocateCrime = useCallback(
    (crimeLabel: string) => {
      const id = labelToCrimeId[crimeLabel];
      if (id) scrollToId(graphAnchorId(id));
    },
    [labelToCrimeId],
  );

  const footerDisclaimer = useMemo(
    () => result?.disclaimer ?? DISCLAIMER,
    [result],
  );

  return (
    <div className="app">
      <header className="app-header">
        <h1>刑法あてはめ判定</h1>
        <p className="header-tagline">
          その出来事は刑法上の犯罪にあたるのか。構成要件に照らして判定します。
        </p>
        <p className="header-disclaimer">{DISCLAIMER}</p>
      </header>

      <main className="app-main">
        {/* ① 事件の入力（送信後は縮小） */}
        <section className={`stage stage-input ${started ? "collapsed" : ""}`}>
          <h2 className="stage-title">① 事件の入力</h2>
          <ConsultForm loading={streaming} onSubmit={handleSubmit} />
        </section>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {/* ② 判定ライブビュー */}
        {started && (
          <section className="stage stage-live" id="judge-live" ref={liveRef}>
            <h2 className="stage-title">② 判定ライブビュー</h2>
            <StepIndicator step={step} />

            {streaming && trace.length === 0 && !streamText && <Loading />}

            <AgentTrace items={trace} />
            <StreamingAnswer text={streamText} streaming={streaming} />
          </section>
        )}

        {/* ③ 判定結果 */}
        {result && (
          <section className="stage stage-result">
            <h2 className="stage-title">③ 判定結果</h2>
            <ResultView
              result={result}
              canLocate={canLocate}
              onLocateCrime={onLocateCrime}
            />
          </section>
        )}
      </main>

      <footer className="app-footer">
        <p>{footerDisclaimer}</p>
      </footer>
    </div>
  );
}

export default App;
