#!/usr/bin/env bash
# Gate `lint`: always passes, always fast. Declared first in factory.yaml so the
# cheapest gate runs first — the ordering the runner must not normalise away.
set -euo pipefail

echo lint >>.factory-gate-order.log

echo "lint: 1 file checked, 0 problems found"
