#!/usr/bin/env bash
# Deploy / update Pitstop WWFC on the VPS (run from server/ on the VM).
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f config.xml ]]; then
  echo "Missing config.xml"
  exit 1
fi

if [[ ! -d payload ]] || [[ -z "$(find payload -type f ! -name 'README.txt' 2>/dev/null | head -1)" ]]; then
  echo "WARNING: payload/ looks empty."
  echo "Build the client/server payloads first with tools/build-wwfc-patch.sh"
  echo "and copy dist/ into server/payload/ before expecting game logins to work."
fi

mkdir -p logs state payload
docker compose build
docker compose up -d
docker compose ps
echo
echo "Server stack is up. Check logs with: docker compose logs -f wwfc"
