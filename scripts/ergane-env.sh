#!/usr/bin/env bash
# ergane-env.sh — decrypt + export the factory worker env from homelab sops secrets.
#
# stdout carries ONLY `export NAME=value` lines; diagnostics go to stderr, so:
#
#   eval "$(scripts/ergane-env.sh)"        # load worker env into current shell
#   uv run python -m factory.worker
#
#   scripts/ergane-env.sh --check          # verify sources; names only, no values
#
# Sources (sops + age, private key ~/.config/sops/age/keys.txt):
#   ~/code/homelab/stacks/llm/secrets.enc.env    -> LITELLM_MASTER_KEY
#   ~/.config/homelab/ergane.enc.env             -> TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
#
# ergane.enc.env lives OUTSIDE any git repo (Bryan's policy: no secrets in
# GitHub, encrypted or not) and is decrypted in memory only — no plaintext
# sibling is ever written for it. Create it once with:
#   sops --age age14tas86t5lyjpn3zzez5ezs5mkfqe9l323lpnvrruhgkj6zzwypxqcgwzrp \
#        ~/.config/homelab/ergane.enc.env
# and edit it later with plain `sops ~/.config/homelab/ergane.enc.env`.
#
# Deliberately NOT exported: ANTHROPIC_API_KEY. The raw Anthropic key belongs in
# the litellm container env only (stacks/llm); agents dispatched by the factory
# get ANTHROPIC_BASE_URL=<proxy> plus a scoped virtual key (ANTHROPIC_AUTH_TOKEN),
# never a provider key.

set -euo pipefail

HOMELAB="${HOMELAB:-$HOME/code/homelab}"
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1

note() { printf '%s\n' "$*" >&2; }
die()  { note "ERROR: $*"; exit 1; }

command -v sops >/dev/null 2>&1 || die "sops not on PATH"
[ -f "${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}" ] \
  || die "age private key missing (~/.config/sops/age/keys.txt)"
[ -d "$HOMELAB" ] || die "homelab repo not found at $HOMELAB (set HOMELAB=)"

# Same contract as `just decrypt <stack>`: refresh the plaintext sibling when
# the encrypted file is newer, mode 600. Returns 1 if the enc file is absent.
decrypt() { # $1=enc $2=plain
  [ -f "$1" ] || return 1
  if [ ! -f "$2" ] || [ "$1" -nt "$2" ]; then
    sops -d "$1" > "$2"
    chmod 600 "$2"
    note "decrypted -> $2"
  fi
}

get() { # $1=env file  $2=name  -> value on stdout, or return 1
  local line
  line=$(grep -E "^$2=" "$1" | tail -n 1) || return 1
  printf '%s' "${line#*=}"
}

emit() { # $1=name $2=value
  if [ "$CHECK" = 1 ]; then
    note "  ok  $1 (${#2} chars)"
  else
    printf 'export %s=%q\n' "$1" "$2"
  fi
}

# -- LiteLLM: Tier 1 fleet proxy (homelab ADR 0035) ---------------------------
llm_enc="$HOMELAB/stacks/llm/secrets.enc.env"
llm_env="$HOMELAB/stacks/llm/.env"
decrypt "$llm_enc" "$llm_env" || die "missing $llm_enc"
master=$(get "$llm_env" LITELLM_MASTER_KEY) || die "LITELLM_MASTER_KEY not in $llm_env"

emit LITELLM_PROXY_URL "${LITELLM_PROXY_URL:-http://localhost:4000}"
emit LITELLM_MASTER_KEY "$master"

# -- Temporal dev server (not secrets; the factory's env contract) ------------
emit TEMPORAL_ADDRESS   "${TEMPORAL_ADDRESS:-localhost:7233}"
emit TEMPORAL_NAMESPACE "${TEMPORAL_NAMESPACE:-factory}"

# -- Telegram escalation bridge -----------------------------------------------
# Out-of-repo secrets: decrypted to memory only, never to a plaintext file.
tg_enc="${ERGANE_SECRETS:-$HOME/.config/homelab/ergane.enc.env}"
if [ -f "$tg_enc" ]; then
  tg_plain=$(sops -d "$tg_enc")
  for name in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID; do
    if line=$(grep -E "^$name=" <<<"$tg_plain" | tail -n 1); then
      emit "$name" "${line#*=}"
    else
      note "  !!  $name missing from $tg_enc — escalations will record undeliverable"
    fi
  done
else
  note "  !!  $tg_enc does not exist yet — Telegram bridge disabled"
  note "      (create it per the new-keys notes: BotFather token + chat id)"
fi
