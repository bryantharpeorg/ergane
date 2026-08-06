#!/usr/bin/env bash
# Gate `typecheck`: always passes. Declared last, and it is the gate that proves
# the runner kept going after the one before it failed or timed out — the
# contract promises one result per declared gate (contracts/activities.md).
set -euo pipefail

echo typecheck >>.factory-gate-order.log

echo "typecheck: Success: no issues found in 1 source file"
