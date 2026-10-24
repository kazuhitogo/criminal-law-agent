import type { CrimeCandidate } from "../api";
import { ConfidenceMeter } from "./ConfidenceMeter";
import { ElementChecklist } from "./ElementChecklist";

// 構成要件チェックカード（SPEC §6.5 / §6.6）。
// 既存 candidate の全項目（crime_label / article / confidence / matched / missing /
// penalty_text / reasoning）を保持し、見せ方のみ変更する。
// カードクリックで②のライブビューの対応グラフ/SPARQL へスクロール（crime_id で対応）。

export function CandidateCard({
  candidate,
  onLocate,
  locatable,
}: {
  candidate: CrimeCandidate;
  onLocate?: () => void;
  locatable?: boolean;
}) {
  return (
    <article className="card judge-card">
      <header className="card-header">
        <h3 className="card-title">
          {candidate.crime_label}
          <span className="card-article">刑法 第{candidate.article}条</span>
        </h3>
        <ConfidenceMeter confidence={candidate.confidence} />
      </header>

      <ElementChecklist
        matched={candidate.matched_elements}
        missing={candidate.missing_elements}
      />

      <div className="card-section">
        <span className="section-label">成立した場合の刑</span>
        <p className="penalty-text">{candidate.penalty_text}</p>
      </div>

      <div className="card-section">
        <span className="section-label">判定の根拠</span>
        <p className="reasoning">{candidate.reasoning}</p>
      </div>

      {locatable && (
        <button type="button" className="locate-link" onClick={onLocate}>
          ② この罪の照合過程（グラフ・SPARQL）を見る →
        </button>
      )}
    </article>
  );
}
