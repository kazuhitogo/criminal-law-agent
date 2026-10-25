// 本文ストリーミング（SPEC §6.2 / §6.3）。
// 表示内容（token 連結）は不変。見出しのみ「判定文の生成」に変更。

export function StreamingAnswer({ text, streaming }: { text: string; streaming: boolean }) {
  if (!text) return null;
  return (
    <section className="streaming-answer">
      <span className="section-label">判定文の生成</span>
      <p className="streaming-text">
        {text}
        {streaming && <span className="caret" aria-hidden="true" />}
      </p>
    </section>
  );
}
