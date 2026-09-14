#!/bin/bash
# Install the market-validation launchd agents on the Mac:
#   com.aidramafactory.market.metrics  (daily 03:30, collects YouTube stats)
#   com.aidramafactory.market.report   (Sunday 09:30, weekly CEO report + Telegram)
# The metrics collector skips cleanly until YT_DATA_API_KEY is present in
# ~/Library/Application Support/AI_Drama_Factory/market_validation.env
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LA_DIR="${HOME}/Library/LaunchAgents"
LOG_DIR="${HOME}/Library/Logs/AI_Drama_Factory"
mkdir -p "${LA_DIR}" "${LOG_DIR}"

for label in com.aidramafactory.market.metrics com.aidramafactory.market.report; do
  cp -f "${SCRIPT_DIR}/${label}.plist" "${LA_DIR}/${label}.plist"
  launchctl unload "${LA_DIR}/${label}.plist" 2>/dev/null || true
  launchctl load "${LA_DIR}/${label}.plist"
  echo "installed: ${label}"
done

launchctl list | grep -i "aidramafactory.market" || true
echo "DONE"
