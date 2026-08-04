#!/usr/bin/env bash
# Gate `test`: passes iff src/calc.py still defines add(). A real check rather
# than a bare `exit 0`, so a test that deletes the function gets a genuine gate
# failure to assert on instead of a staged one.
set -euo pipefail

echo test >>.factory-gate-order.log

source_text=$(<src/calc.py)
if [[ $source_text != *"def add("* ]]; then
	echo "test: src/calc.py no longer defines add()" >&2
	exit 1
fi

echo "test: 1 passed"
