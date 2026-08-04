#!/usr/bin/env bash
# Ralph loop over specs/<spec>/tasks.md.
# Usage: ./ralph/ralph.sh <spec-dir-name>   (from repo root; MAX_ITER=40 by default)
#        MAX_ITER=5 ./ralph/ralph.sh 002-verification-gating   (bounded trial run)
set -euo pipefail
cd "$(dirname "$0")/.."

SPEC="${1:?usage: ralph.sh <spec-dir-name>, e.g. 002-verification-gating}"
TASKS="specs/$SPEC/tasks.md"
[ -f "$TASKS" ] || { echo "no such tasks file: $TASKS" >&2; exit 2; }
MAX_ITER="${MAX_ITER:-40}"
LOG_DIR=ralph/logs
mkdir -p "$LOG_DIR"
PROMPT="$(sed "s/{{SPEC}}/$SPEC/g" ralph/PROMPT.md)"

for i in $(seq 1 "$MAX_ITER"); do
  if ! grep -q '^- \[ \]' "$TASKS"; then
    echo "=== all tasks checked after $((i-1)) iterations ==="
    exit 0
  fi
  echo "=== ralph iteration $i / $MAX_ITER ($SPEC) ==="
  log="$LOG_DIR/$SPEC-iter-$(printf '%03d' "$i").log"
  claude -p "$PROMPT" \
    --dangerously-skip-permissions \
    2>&1 | tee "$log" || true

  if grep -q 'RALPH_DONE' "$log"; then
    echo "=== done ==="
    exit 0
  fi
  if grep -q 'RALPH_BLOCKED' "$log"; then
    echo "=== blocked — see specs/$SPEC/BLOCKED.md and $log ==="
    exit 1
  fi
done
echo "=== MAX_ITER=$MAX_ITER reached with unchecked tasks remaining ==="
exit 1
