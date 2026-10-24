import type { Confidence } from "../api";

const LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

export function ConfidenceBadge({ confidence }: { confidence: Confidence | string }) {
  const key = String(confidence).toLowerCase();
  const label = LABELS[key] ?? confidence;
  return <span className={`badge badge-${key}`}>確信度: {label}</span>;
}
