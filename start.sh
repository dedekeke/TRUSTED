#!/usr/bin/env bash
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
ROOT="${PETS_ROOT:-$(dirname "$SRC")}"
PY="$ROOT/.venv/bin/python"
JEV_PY="$SRC/.venv-jev/bin/python"
JEV_MODEL="$ROOT/models/AutoTrust-JEV-27B-v1.1-mlx-4bit"
VITE="$SRC/client/node_modules/.bin/vite"

die() { echo "start.sh: $*" >&2; exit 1; }
busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

[ -n "${PRIVACY_TOOL_HMAC_KEY:-}" ] || die "set PRIVACY_TOOL_HMAC_KEY (the HMAC key) in the environment"
[ -x "$PY" ] || die "no virtualenv at $PY"
[ -x "$VITE" ] || die "no client deps: run 'npm install' in $SRC/client"
MODEL="${DETECT_MODEL:-$(ls -td "$ROOT"/outputs/*/model 2>/dev/null | while read -r d; do [ -f "$d/model.pkl" ] && echo "$d" && break; done)}"
[ -n "$MODEL" ] && [ -f "$MODEL/model.pkl" ] || die "no detect model found; set DETECT_MODEL=<dir with model.pkl>"
RUNS="${RUNS:-$ROOT/outputs/runs-$(date -u +%Y%m%dT%H%M%SZ)}"
[ -e "$RUNS" ] && die "$RUNS already exists; every start writes to a fresh runs dir"
busy 8000 && die "port 8000 is in use (an old server.api?); stop it first"
busy 5174 && die "port 5174 is in use (an old Vite?); stop it first"

pids=()
trap 'kill ${pids[@]+"${pids[@]}"} 2>/dev/null; wait' EXIT INT TERM

if [ -n "${NO_JEV:-}" ]; then
  echo "JEV: skipped (NO_JEV); Detect runs tiers 1-2 only"
elif busy 8001; then
  echo "JEV: already listening on :8001, reusing it"
elif [ -x "$JEV_PY" ] && [ -d "$JEV_MODEL" ]; then
  (cd "$SRC" && exec "$JEV_PY" -m jev27b_mlx serve "$JEV_MODEL" --port 8001) & pids+=($!)
  echo "JEV: starting on :8001 (model load can take a minute)"
else
  echo "JEV: $JEV_PY or $JEV_MODEL missing, skipped; Detect runs tiers 1-2 only (see README)"
fi

(cd "$SRC" && exec "$PY" -m server.api --root "$ROOT" --model "$MODEL" --runs "$RUNS" --port 8000 --guard) & pids+=($!)

(cd "$SRC/client" && VITE_API_BASE_URL=/ exec "$VITE" --host --port 5174 --strictPort) & pids+=($!)

echo "model $MODEL"
echo "runs  $RUNS"
echo "UI    http://localhost:5174/  (Ctrl-C stops everything started here)"
while :; do
  for p in "${pids[@]}"; do kill -0 "$p" 2>/dev/null || exit 1; done
  sleep 2
done
