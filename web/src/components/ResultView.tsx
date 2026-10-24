import type { ConsultationResult } from "../api";
import { CandidateCard } from "./CandidateCard";

// 判定結果ビュー（SPEC §6.5 / §6.6）。
// 判定ヘッダーは no_crime と candidates 数からフロント側で導出する（新データなし）。
// onLocateCrime: 罪名から②のライブビューの対応グラフへスクロールする結線。
//   引数の crime_label に一致する graph(crime_id) が無い場合は null を返し、
//   その罪のリンクは出さない（無効リンクを作らない）。

export function ResultView({
  result,
  canLocate,
  onLocateCrime,
}: {
  result: ConsultationResult;
  canLocate?: (crimeLabel: string) => boolean;
  onLocateCrime?: (crimeLabel: string) => void;
}) {
  const hasCandidates = !result.no_crime && result.candidates.length > 0;
  const count = result.candidates.length;

  return (
    <section className="result" id="judge-result">
      {/* 判定ヘッダー（導出のみ） */}
      <div className={`judge-header ${hasCandidates ? "judge-hit" : "judge-miss"}`}>
        <span className="judge-verdict">
          {hasCandidates
            ? "犯罪が成立しうる"
            : "罪に問うは難し"}
        </span>
        {hasCandidates && (
          <span className="judge-sub">構成要件に照らし {count} 件の罪に該当の可能性</span>
        )}
      </div>

      <div className="summary">
        <span className="section-label">事件の要約</span>
        <p>{result.summary}</p>
      </div>

      {hasCandidates ? (
        <div className="cards">
          {result.candidates.map((c, i) => {
            const locatable = canLocate?.(c.crime_label) ?? false;
            return (
              <CandidateCard
                key={`${c.article}-${i}`}
                candidate={c}
                locatable={locatable}
                onLocate={() => onLocateCrime?.(c.crime_label)}
              />
            );
          })}
        </div>
      ) : (
        <div className="no-crime">
          <strong>刑法上は該当する罪が見当たりません。</strong>
          <p>
            ご相談の内容は、刑事上の犯罪構成要件を満たさない可能性が高いと考えられます
            （民事上の問題にとどまる場合などがあります）。
          </p>
        </div>
      )}
    </section>
  );
}
