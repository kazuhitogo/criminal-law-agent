// 構成要件チェックリスト + 充足ゲージ（SPEC §6.5 / §6.6）。
// matched_elements=「✓ 満たしうる」、missing_elements=「？ 要確認／不足」。
// ゲージは matched /(matched + missing) の件数比（既存配列から導出するのみ、新データなし）。
// 各行の文字列は既存配列をそのまま表示する。

export function ElementChecklist({
  matched,
  missing,
}: {
  matched: string[];
  missing: string[];
}) {
  const total = matched.length + missing.length;
  const ratio = total > 0 ? matched.length / total : 0;

  return (
    <div className="element-checklist">
      <div className="gauge-head">
        <span className="section-label">構成要件の充足</span>
        <span className="gauge-count">
          {matched.length} / {total}
        </span>
      </div>
      <div
        className="gauge"
        role="meter"
        aria-label="構成要件の充足状況"
        aria-valuenow={matched.length}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuetext={`${total} 件中 ${matched.length} 件が満たしうる`}
      >
        <span className="gauge-fill" style={{ ["--ratio" as string]: ratio }} />
      </div>

      {matched.length > 0 && (
        <ul className="check-list matched">
          {matched.map((el, i) => (
            <li key={`m-${i}`}>
              <span className="check-mark" aria-hidden="true">
                ✓
              </span>
              <span className="check-text">{el}</span>
              <span className="sr-only">（満たしうる）</span>
            </li>
          ))}
        </ul>
      )}

      {missing.length > 0 && (
        <ul className="check-list missing">
          {missing.map((el, i) => (
            <li key={`x-${i}`}>
              <span className="check-mark" aria-hidden="true">
                ？
              </span>
              <span className="check-text">{el}</span>
              <span className="sr-only">（要確認／不足）</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
