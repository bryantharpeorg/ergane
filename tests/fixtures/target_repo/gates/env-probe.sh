#!/usr/bin/env bash
# Gate `test`, environment-probe variant: reports what the gate subprocess can
# see, and passes. Env scrubbing is only observable from inside the child, so the
# child has to say — a test that inspected the parent's environment would assert
# nothing about the gate at all.
#
# `${VAR-<unset>}` (no colon) distinguishes "not exported" from "exported empty";
# both are acceptable scrubbing, and both are visible here. `declare -x` is a
# builtin, so the full listing works even if PATH were scrubbed to nothing.
set -uo pipefail

echo test >>.factory-gate-order.log

echo "LITELLM_MASTER_KEY=[${LITELLM_MASTER_KEY-<unset>}]"
echo "TELEGRAM_BOT_TOKEN=[${TELEGRAM_BOT_TOKEN-<unset>}]"
echo "LITELLM_PROXY_URL=[${LITELLM_PROXY_URL-<unset>}]"
echo "PATH=[${PATH-<unset>}]"
echo "HOME=[${HOME-<unset>}]"
echo "PWD=[${PWD-<unset>}]"

echo "--- exported environment ---"
declare -x
