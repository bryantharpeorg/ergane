#!/usr/bin/env bash
# Gate `test`, failing variant: exits 3 — a distinct non-zero code, so a test can
# assert the exit code was *reported* rather than merely that something was
# truthy. Writes to both streams because `output_tail` is the retry feedback the
# next attempt reads (SC-004), and a runner that captured only stdout would drop
# exactly the line that says what broke.
set -uo pipefail

echo test >>.factory-gate-order.log

echo "test: 2 passed, 1 failed"
echo "E       assert add(2, 2) == 5" >&2

exit 3
