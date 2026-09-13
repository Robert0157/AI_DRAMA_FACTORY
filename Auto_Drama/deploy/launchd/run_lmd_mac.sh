#!/usr/bin/env bash
# ============================================================================
# run_lmd_mac.sh — LocalMiniDrama 後端啟動包裝 (Mac mini 生產用)
# 由 launchd (com.auto-drama.lmd) 呼叫。工作：
#   1. 等待外接 SSD 掛載
#   2. 解析 Node 絕對路徑 (Apple Silicon: /opt/homebrew, Intel: /usr/local)
#   3. 於 backend-node 啟動 npm start
# 編輯下方 MAC_ROOT / NODE_BIN 以符合你的環境。
# ============================================================================
set -euo pipefail

MAC_ROOT="${AUTO_DRAMA_MAC_ROOT:-/Volumes/AI_Workspace/AI_DRAMA_FACTORY}"
BACKEND_DIR="$MAC_ROOT/LocalMiniDrama-main/backend-node"
LOG_DIR="$MAC_ROOT/Auto_Drama/logs"

# --- 等待外接 SSD 掛載（最多 60 秒）---
for i in $(seq 1 60); do
  if mount | grep -q "/Volumes/AI_Workspace"; then break; fi
  if [ "$i" -eq 60 ]; then
    echo "[run_lmd] SSD 未掛載，放棄啟動" >&2
    exit 1
  fi
  sleep 1
done

# --- Node 解析：優先環境變數，再依晶片自動偵測 ---
if [ -n "${NODE_BIN:-}" ]; then
  NODE_BIN_PATH="$NODE_BIN"
elif [ -x /opt/homebrew/bin/node ]; then        # Apple Silicon
  NODE_BIN_PATH=/opt/homebrew/bin/node
elif [ -x /usr/local/bin/node ]; then           # Intel
  NODE_BIN_PATH=/usr/local/bin/node
else
  echo "[run_lmd] 找不到 node" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
export PATH="$(dirname "$NODE_BIN_PATH"):$PATH"

echo "[run_lmd] node=$NODE_BIN_PATH backend=$BACKEND_DIR"
cd "$BACKEND_DIR"
# launchd 沒有 login shell，需明確指向 npm-cli.js 以防 PATH 差異
NPM_CLI="$(dirname "$NODE_BIN_PATH")/../lib/node_modules/npm/bin/npm-cli.js"
if [ ! -f "$NPM_CLI" ]; then NPM_CLI="$(dirname "$NODE_BIN_PATH")/npm"; fi

exec "$NODE_BIN_PATH" "$NPM_CLI" start
