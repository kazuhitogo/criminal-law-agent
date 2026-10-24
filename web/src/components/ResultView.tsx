import type { ConsultationResult } from "../api";
import { CandidateCard } from "./CandidateCard";

export function ResultView({ result }: { result: ConsultationResult }) {
  return (
    <section className="result">
      <div className="summary">
        <span className="section-label">相談の要約</span>
        <p>{result.summary}</p>
      </div>

      {result.no_crime || result.candidates.length === 0 ? (
        <div className="no-crime">
          <strong>刑法上は該当する罪が見当たりません。</strong>
          <p>
            ご相談の内容は、刑事上の犯罪構成要件を満たさない可能性が高いと考えられます
            （民事上の問題にとどまる場合などがあります）。
          </p>
        </div>
      ) : (
        <div className="cards">
          {result.candidates.map((c, i) => (
            <CandidateCard key={`${c.article}-${i}`} candidate={c} />
          ))}
        </div>
      )}
    </section>
  );
}
