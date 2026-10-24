export function StreamingAnswer({ text, streaming }: { text: string; streaming: boolean }) {
  if (!text) return null;
  return (
    <section className="streaming-answer">
      <span className="section-label">回答（ストリーミング）</span>
      <p className="streaming-text">
        {text}
        {streaming && <span className="caret" aria-hidden="true" />}
      </p>
    </section>
  );
}
