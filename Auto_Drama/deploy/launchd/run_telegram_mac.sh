#!/usr/bin/env bash
# ============================================================================
# run_telegram_mac.sh — Auto_Drama Telegram 遠端控制啟動包裝 (Mac 生產用)
# 由 launchd (com.auto-drama.telegram) 呼叫。
#   1. 等待外接 SSD 掛載
#   2. source 環境金鑰檔 (deploy/env/auto_drama.env)
#   3. 啟動 Auto_Drama venv 內 python run.py telegram
# 編輯下方 MAC_ROOT 以符合你的環境（金鑰放 env 檔，勿寫死於此）。
# ============================================================================
set -euo pipefail

MAC_ROOT="${AUTO_DRAMA_MAC_ROOT:-/Volumes/AI_Workspace/AI_DRAMA_FACTORY}"
AUTO_DIR="$MAC_ROOT/Auto_Drama"
ENV_FILE="$AUTO_DIR/deploy/env/auto_drama.env"
LOG_DIR="$AUTO_DIR/logs"
VENV_PY="$AUTO_DIR/venv/bin/python"

# --- 等待外接 SSD 掛載（最多 60 秒）---
for i in $(seq 1 60); do
  if mount | grep -q "/Volumes/AI_Workspace"; then break; fi
  if [ "$i" -eq 60 ]; then
    echo "[run_telegram] SSD 未掛載，放棄啟動" >&2
    exit 1
  fi
  sleep 1
done

mkdir -p "$LOG_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "[run_telegram] 找不到 env 檔: $ENV_FILE（請從 auto_drama.env.example 複製並填入金鑰）" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [ ! -x "$VENV_PY" ]; then
  echo "[run_telegram] 找不到 venv python: $VENV_PY（請先在 Mac 端建立 venv 並 pip install）" >&2
  exit 1
fi

cd "$AUTO_DIR"
exec "$VENV_PY" run.py telegram --token "$TELEGRAM_BOT_TOKEN"
