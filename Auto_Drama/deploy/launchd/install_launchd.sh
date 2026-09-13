#!/usr/bin/env bash
# ============================================================================
# install_launchd.sh — 安裝 Auto_Drama 兩個 LaunchAgent (Mac mini)
#
# 前置: 已把 Auto_Drama 部署到 Mac (/Volumes/AI_Workspace/AI_DRAMA_FACTORY)
#       已編輯 run_lmd_mac.sh / run_telegram_mac.sh 的 MAC_ROOT
#       已建立 deploy/env/auto_drama.env
# 用法:
#   ./install_launchd.sh            # 安裝並啟動兩個 agent
#   ./install_launchd.sh uninstall # 停止並移除
# ============================================================================
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$HOME/Library/LaunchAgents"
AGENTS=("com.auto-drama.lmd" "com.auto-drama.telegram")
MAC_ROOT="${AUTO_DRAMA_MAC_ROOT:-/Volumes/AI_Workspace/AI_DRAMA_FACTORY}"

mkdir -p "$AGENT_DIR"
# 讓包裝腳本可執行
chmod +x "$SRC_DIR"/run_*.sh

if ! mount | grep -q "/Volumes/AI_Workspace"; then
  echo "[install] 警告: 外接 SSD 未掛載（/Volumes/AI_Workspace）" >&2
fi

if [ "${1:-}" = "uninstall" ]; then
  for name in "${AGENTS[@]}"; do
    plist="$AGENT_DIR/$name.plist"
    if launchctl list | grep -q "$name"; then
      launchctl unload -w "$plist" 2>/dev/null || true
    fi
    rm -f "$plist"
    echo "[install] 已移除 $name"
  done
  exit 0
fi

# 檢查 plist 內路徑是否與實際一致
for name in "${AGENTS[@]}"; do
  if ! grep -q "$MAC_ROOT" "$SRC_DIR/$name.plist"; then
    echo "[install] 錯誤: $name.plist 內路徑與 MAC_ROOT ($MAC_ROOT) 不符，請先編輯。" >&2
    exit 1
  fi
done

for name in "${AGENTS[@]}"; do
  cp "$SRC_DIR/$name.plist" "$AGENT_DIR/"
  launchctl unload -w "$AGENT_DIR/$name.plist" 2>/dev/null || true
  launchctl load -w "$AGENT_DIR/$name.plist"
  echo "[install] 已啟動 $name"
done

echo ""
echo "[install] 完成。狀態查詢:"
echo "  launchctl list | grep auto-drama"
echo "  tail -f $MAC_ROOT/Auto_Drama/logs/lmd.stdout.log"
echo "  tail -f $MAC_ROOT/Auto_Drama/logs/telegram.stdout.log"
echo ""
echo "[install] 立即測試 Telegram: 對你的 bot 傳 /status"
