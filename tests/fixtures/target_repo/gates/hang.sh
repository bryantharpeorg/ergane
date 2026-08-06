#!/usr/bin/env bash
# Gate `test`, hanging variant: sleeps far past any timeout a test would declare,
# and terminates on SIGTERM like a well-behaved process. Prints first, so the
# tail proves the runner captured the output of a process it later killed rather
# than throwing the pipe away with the child.
set -uo pipefail

echo test >>.factory-gate-order.log

echo "hang: started, sleeping"
sleep 30
echo "hang: finished"
