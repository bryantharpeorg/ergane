#!/usr/bin/env bash
# Ralph loop over specs/001-usage-tracking/tasks.md.
# Usage: ./ralph/ralph.sh            (from repo root; MAX_ITER=40 by default)
#        MAX_ITER=5 ./ralph/ralph.sh (bounded trial run)
set -euo pipefail
cd "$(dirname "$0")/.."

TASKS=specs/001-usage-tracking/tasks.md
MAX_ITER="${MAX_ITER:-40}"
LOG_DIR=ralph/logs
mkdir -p "$LOG_DIR"

for i in $(seq 1 "$MAX_ITER"); do
  if ! grep -q '^- \[ \]' "$TASKS"; then
    echo "=== all tasks checked after $((i-1)) iterations ==="
    exit 0
  fi
  echo "=== ralph iteration $i / $MAX_ITER ==="
  log="$LOG_DIR/iter-$(printf '%03d' "$i").log"
  claude -p "$(cat ralph/PROMPT.md)" \
    --dangerously-skip-permissions \
    2>&1 | tee "$log" || true

  if grep -q 'RALPH_DONE' "$log"; then
    echo "=== done ==="
    exit 0
  fi
  if grep -q 'RALPH_BLOCKED' "$log"; then
    echo "=== blocked — see specs/001-usage-tracking/BLOCKED.md and $log ==="
    exit 1
  fi
done
echo "=== MAX_ITER=$MAX_ITER reached with unchecked tasks remaining ==="
exit 1
