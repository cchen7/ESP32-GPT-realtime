#!/usr/bin/env bash
# One-shot rotation of the gpt-realtime2-demo-sp client secret.
# Run locally as a user who OWNS the app registration (e.g. after `az login`).
# Writes the new credentials into ./.env (chmod 600).
#
#   ./rotate_secret.sh
#
set -euo pipefail

APP_ID="${APP_ID:-8a84ac49-19e3-4d71-9509-3e4ccfedfeaa}"
LIFETIME_DAYS="${LIFETIME_DAYS:-29}"   # tenant policy caps secret lifetime at ~30 days
ENV_FILE="$(cd "$(dirname "$0")" && pwd)/.env"

command -v az >/dev/null 2>&1 || { echo "ERROR: az CLI not found." >&2; exit 1; }
az account show >/dev/null 2>&1 || { echo "ERROR: not logged in. Run 'az login' first." >&2; exit 1; }

END_DATE=$(python3 -c "import datetime;print((datetime.datetime.now(datetime.UTC)+datetime.timedelta(days=$LIFETIME_DAYS)).strftime('%Y-%m-%dT%H:%M:%SZ'))")
echo "Rotating secret for app $APP_ID (expires $END_DATE)..."

RESULT=$(az ad app credential reset \
  --id "$APP_ID" \
  --end-date "$END_DATE" \
  --display-name "rotated-$(date -u +%Y%m%d)" \
  -o json)

TMP=$(mktemp)
printf '%s' "$RESULT" > "$TMP"
python3 - "$TMP" "$ENV_FILE" "$END_DATE" <<'PY'
import json, os, sys
res = json.load(open(sys.argv[1]))
env_file, end = sys.argv[2], sys.argv[3]
content = (
    "# Service principal credentials (rotated). KEEP PRIVATE — do not commit.\n"
    f"# Secret expires {end}\n"
    f"AZURE_TENANT_ID={res['tenant']}\n"
    f"AZURE_CLIENT_ID={res['appId']}\n"
    f"AZURE_CLIENT_SECRET={res['password']}\n"
)
with open(env_file, "w") as f:
    f.write(content)
os.chmod(env_file, 0o600)
print(f"Wrote {env_file}")
PY
rm -f "$TMP"
echo "Done. New secret valid until $END_DATE."
