// 判定ライブビューのステップ・インジケータ（SPEC §6.5）。
// 「事実の把握 → 候補の抽出 → 構成要件の照合 → 判定」の 4 段を、
// 受信ストリームイベントから導出した進行度（App 側で算出）に応じて点灯する。
// 表示情報は増やさない（ストリームイベント種別の可視化のみ）。

export type JudgeStep = 0 | 1 | 2 | 3 | 4;
// 0: 未開始 / 1: 事実の把握 / 2: 候補の抽出 / 3: 構成要件の照合 / 4: 判定

const STEPS: { key: JudgeStep; label: string }[] = [
  { key: 1, label: "事実の把握" },
  { key: 2, label: "候補の抽出" },
  { key: 3, label: "構成要件の照合" },
  { key: 4, label: "判定" },
];

export function StepIndicator({ step }: { step: JudgeStep }) {
  return (
    <ol className="step-indicator" aria-label="判定の進行状況">
      {STEPS.map(({ key, label }, i) => {
        const state =
          step > key ? "done" : step === key ? "active" : "pending";
        return (
          <li
            key={key}
            className={`step step-${state}`}
            aria-current={state === "active" ? "step" : undefined}
          >
            <span className="step-dot" aria-hidden="true">
              {state === "done" ? "✓" : key}
            </span>
            <span className="step-label">{label}</span>
            {i < STEPS.length - 1 && (
              <span className="step-bar" aria-hidden="true" />
            )}
          </li>
        );
      })}
    </ol>
  );
}
