#!/usr/bin/env bash
# Gate `test`, noisy variant: emits ~110 KiB, well past the 32 KiB `output_tail`
# cap, then fails. A real failing test suite is verbose, and the cap is what
# stops one from being copied into workflow state, an escalation message and the
# evidence store.
#
# The two markers are the assertion surface: NOISE-HEAD is printed first and must
# be gone from a correctly-capped tail; NOISE-TAIL is printed last and must
# survive, because the *end* of the output is where the failure is explained.
set -uo pipefail

echo test >>.factory-gate-order.log

echo "NOISE-HEAD first line of output"

line=1
while ((line <= 2000)); do
	printf 'noise %04d: %s\n' "$line" "----------------------------------------"
	line=$((line + 1))
done

echo "NOISE-TAIL last line of output"

exit 1
