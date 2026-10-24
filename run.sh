#!/usr/bin/env bash
#
# 刑法オントロジー法律相談エージェント — 一括起動スクリプト
#
# ontology のビルド/依存解決 → agent API(FastAPI) → web(Vite) を順に立ち上げる。
# Ctrl+C で両サーバをまとめて停止する。
#
# 使い方:
#   ./run.sh                       # そのまま起動（AWS 認証は環境変数で）
#   AWS_PROFILE=dev-vm ./run.sh    # プロファイル指定で起動
#
# 環境変数（任意, 既定値あり）:
#   AGENT_PORT               agent API ポート        （既定 8099）
#   WEB_PORT                 web 開発サーバポート     （既定 5173）
#   AWS_PROFILE / AWS_REGION Bedrock 認証・リージョン （boto3 既定解決）
#   CRIMINAL_AGENT_MODEL_ID  Bedrock モデル ID        （agent 側既定を使用）
#   SKIP_SETUP=1             依存解決/ビルドを省略して高速起動
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_PORT="${AGENT_PORT:-8099}"
WEB_PORT="${WEB_PORT:-5173}"

# web から参照する API ベース URL（未指定なら agent ポートに合わせる）
export VITE_API_BASE="${VITE_API_BASE:-http://127.0.0.1:${AGENT_PORT}}"

log()  { printf '\033[1;36m[run]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[run]\033[0m %s\n' "$*" >&2; }

# --- 前提コマンド確認 ---
command -v uv  >/dev/null 2>&1 || { err "uv が見つからない。https://docs.astral.sh/uv/ を参照。"; exit 1; }
command -v npm >/dev/null 2>&1 || { err "npm が見つからない。Node.js をインストールする。"; exit 1; }

# --- セットアップ（冪等）---
if [[ "${SKIP_SETUP:-0}" != "1" ]]; then
  log "ontology: 依存解決とオントロジービルド"
  (cd "$ROOT_DIR/ontology" && uv sync --quiet && uv run python -m criminal_ontology.build >/dev/null)

  log "agent: 依存解決"
  (cd "$ROOT_DIR/agent" && uv sync --quiet)

  if [[ ! -d "$ROOT_DIR/web/node_modules" ]]; then
    log "web: npm install"
    (cd "$ROOT_DIR/web" && npm install --silent)
  fi
else
  log "SKIP_SETUP=1: 依存解決/ビルドを省略"
fi

# --- 子プロセス管理 ---
PIDS=()

# 指定 PID とその子孫を再帰的に kill する（uv/npm のラッパ越しの孫まで確実に停止）。
kill_tree() {
  local pid="$1"
  # 子を先に辿る
  local child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill "$pid" 2>/dev/null || true
}

cleanup() {
  # 二重実行防止
  trap - INT TERM EXIT
  log "停止中..."
  for pid in "${PIDS[@]}"; do
    kill_tree "$pid"
  done
  wait 2>/dev/null || true
  log "停止した。"
}
trap cleanup INT TERM EXIT

# --- agent API 起動 ---
log "agent API を起動: http://127.0.0.1:${AGENT_PORT}  (profile=${AWS_PROFILE:-<default>})"
(
  cd "$ROOT_DIR/agent"
  uv run uvicorn criminal_agent.api:app --host 127.0.0.1 --port "$AGENT_PORT"
) &
PIDS+=($!)

# --- web 起動 ---
log "web UI を起動: http://127.0.0.1:${WEB_PORT}  (API=${VITE_API_BASE})"
(
  cd "$ROOT_DIR/web"
  npm run dev -- --host 127.0.0.1 --port "$WEB_PORT" --strictPort
) &
PIDS+=($!)

log "両サーバを起動した。ブラウザで http://127.0.0.1:${WEB_PORT} を開く。Ctrl+C で停止。"

# いずれかのプロセスが終了したら全体を終了
wait -n 2>/dev/null || wait
