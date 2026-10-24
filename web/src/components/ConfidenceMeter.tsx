import type { Confidence } from "../api";

// 確信度メーター（SPEC §6.5 / §6.6）。
// 既存 confidence（high/medium/low）を「同値のまま」メーター表現にするのみ。
// 新しいスコアや数値は足さない。表示ラベルは従来バッジと同じ「高/中/低」。

const LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

// メーターの塗り割合は confidence の順序対応のみ（新データではなく表現）。
const FILL: Record<string, number> = {
  high: 1,
  medium: 0.66,
  low: 0.33,
};

export function ConfidenceMeter({ confidence }: { confidence: Confidence | string }) {
  const key = String(confidence).toLowerCase();
  const label = LABELS[key] ?? String(confidence);
  const fill = FILL[key] ?? 0.33;

  return (
    <div className="confidence-meter">
      <span className="section-label">確信度</span>
      <div
        className={`meter meter-${key}`}
        role="meter"
        aria-label="確信度"
        aria-valuetext={label}
        aria-valuenow={Math.round(fill * 3)}
        aria-valuemin={1}
        aria-valuemax={3}
      >
        <span className="meter-fill" style={{ ["--fill" as string]: fill }} />
      </div>
      <span className={`meter-value meter-value-${key}`}>{label}</span>
    </div>
  );
}
