export function Loading() {
  return (
    <div className="loading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>刑法オントロジーを照会しています...</span>
    </div>
  );
}
