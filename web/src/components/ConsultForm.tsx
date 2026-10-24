import { useState } from "react";

interface Props {
  loading: boolean;
  onSubmit: (text: string) => void;
}

const EXAMPLES = [
  "財布を盗まれた",
  "隣人に殴られた",
  "SNSで悪口を書かれた",
  "貸した金が返ってこない",
];

export function ConsultForm({ loading, onSubmit }: Props) {
  const [text, setText] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (t && !loading) onSubmit(t);
  };

  return (
    <form className="consult-form" onSubmit={submit}>
      <label htmlFor="consult-text" className="form-label">
        起きた出来事を入力してください
      </label>
      <textarea
        id="consult-text"
        className="consult-textarea"
        rows={5}
        placeholder="例: 知らない人に突然殴られて怪我をした"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={loading}
      />
      <div className="examples">
        <span className="examples-label">例で試す:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            className="example-chip"
            onClick={() => setText(ex)}
            disabled={loading}
          >
            {ex}
          </button>
        ))}
      </div>
      <button type="submit" className="submit-btn" disabled={loading || !text.trim()}>
        {loading ? "判定中..." : "判定を開始する"}
      </button>
    </form>
  );
}
