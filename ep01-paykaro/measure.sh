#!/usr/bin/env bash
# Run each scenario from a clean start for 7 minutes and print what customers saw at 4 and 7 minutes.
# Usage: ./measure.sh [scenario ...]   (default: all). Needs LLM_API_KEY in the environment for the bot.
set -euo pipefail
cd "$(dirname "$0")"
declare -A S=(
  [bot-off]="BOT_ENABLED=false"
  [bot-on]="BOT_ENABLED=true"
  [cooldown-only]="BOT_ENABLED=true RESEND_COOLDOWN_S=120"
  [bypass-only]="BOT_ENABLED=true HANDSHAKE_DELAY_S=0.05"
  [all-fixes]="BOT_ENABLED=true HANDSHAKE_DELAY_S=0.05 RESEND_COOLDOWN_S=120 SMS_RESEND_QUOTA_PER_MIN=20"
)
names=("$@"); [ ${#names[@]} -eq 0 ] && names=(bot-off bot-on cooldown-only bypass-only all-fixes)
docker compose up -d --build jaeger prometheus collector grafana obi >/dev/null 2>&1
for name in "${names[@]}"; do
  docker compose rm -sf users otp-service sms-vendor egress-proxy carrier >/dev/null 2>&1
  env ${S[$name]} docker compose up -d >/dev/null 2>&1
  for at in 240 420; do
    sleep $(( at == 240 ? 240 : 180 ))
    echo "$name @$((at/60))min: $(docker compose logs users --tail 1 | sed 's/.*| //') | vendor $(curl -s localhost:8003/account)"
  done
done
docker compose stop users >/dev/null 2>&1
