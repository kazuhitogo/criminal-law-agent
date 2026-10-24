import type { CrimeCandidate } from "../api";
import { ConfidenceBadge } from "./ConfidenceBadge";

export function CandidateCard({ candidate }: { candidate: CrimeCandidate }) {
  return (
    <article className="card">
      <header className="card-header">
        <h3 className="card-title">
          {candidate.crime_label}
          <span className="card-article">刑法 第{candidate.article}条</span>
        </h3>
        <ConfidenceBadge confidence={candidate.confidence} />
      </header>

      <div className="card-section">
        <span className="section-label">法定刑</span>
        <p className="penalty-text">{candidate.penalty_text}</p>
      </div>

      {candidate.matched_elements.length > 0 && (
        <div className="card-section">
          <span className="section-label">満たしうる構成要件</span>
          <ul className="element-list matched">
            {candidate.matched_elements.map((el, i) => (
              <li key={i}>{el}</li>
            ))}
          </ul>
        </div>
      )}

      {candidate.missing_elements.length > 0 && (
        <div className="card-section">
          <span className="section-label">不足・要確認の構成要件</span>
          <ul className="element-list missing">
            {candidate.missing_elements.map((el, i) => (
              <li key={i}>{el}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="card-section">
        <span className="section-label">理由</span>
        <p className="reasoning">{candidate.reasoning}</p>
      </div>
    </article>
  );
}
