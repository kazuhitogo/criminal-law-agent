import { useRef, useState } from "react";
import "./App.css";
import {
  consultStream,
  ApiError,
  type ConsultationResult,
  type StreamEvent,
} from "./api";
import { ConsultForm } from "./components/ConsultForm";
import { Loading } from "./components/Loading";
import { ResultView } from "./components/ResultView";
import { StreamingAnswer } from "./components/StreamingAnswer";
import { AgentTrace, isTraceItem, type TraceItem } from "./components/AgentTrace";

const DISCLAIMER =
  "本システムは日本の刑法に関する一般的な情報提供を目的としたものであり、個別事案に対する法的助言ではありません。実際の法的対応については弁護士等の専門家にご相談ください。";

function App() {
  const [streaming, setStreaming] = useState(false);
  const [trace, setTrace] = useState<TraceItem[]>([]);
  const [streamText, setStreamText] = useState("");
  const [result, setResult] = useState<ConsultationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const handleEvent = (ev: StreamEvent) => {
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
  };

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

  return (
    <div className="app">
      <header className="app-header">
        <h1>刑法相談</h1>
        <p className="header-disclaimer">{DISCLAIMER}</p>
      </header>

      <main className="app-main">
        <ConsultForm loading={streaming} onSubmit={handleSubmit} />

        {streaming && trace.length === 0 && !streamText && <Loading />}

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {started && <AgentTrace items={trace} />}

        <StreamingAnswer text={streamText} streaming={streaming} />

        {result && <ResultView result={result} />}
      </main>

      <footer className="app-footer">
        <p>{result?.disclaimer ?? DISCLAIMER}</p>
      </footer>
    </div>
  );
}

export default App;
