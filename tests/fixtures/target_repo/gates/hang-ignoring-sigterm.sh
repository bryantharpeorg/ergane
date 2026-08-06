#!/usr/bin/env bash
# Gate `test`, SIGTERM-defying variant: ignores the polite signal, so only the
# SIGKILL escalation (R3: SIGTERM, then SIGKILL after the grace period) ends it.
# A runner that sent SIGTERM and assumed death would hang here forever, which is
# the failure this fixture exists to make visible.
#
# The wait loop is deliberate: `sleep` runs as a child, and a child killed by a
# signal sent to the process group must not end the script either. Bash itself is
# the thing that has to survive until SIGKILL.
set -uo pipefail

trap '' TERM INT

echo test >>.factory-gate-order.log

echo "defy: ignoring SIGTERM"
deadline=$((SECONDS + 30))
while ((SECONDS < deadline)); do
	sleep 1
done
echo "defy: finished"
