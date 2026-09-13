#!/usr/bin/env bash
# ============================================================================
# Auto_Drama — Mac 端「拉取」同步腳本（備援方案）
# 若 Windows 端有開啟 OpenSSH Server，可讓 Mac 主動 rsync 拉取。
# 一般情況建議直接用 Windows 端 sync_to_mac.ps1 推送即可。
#
# 用法:
#   ./sync_to_mac.sh <win_user> <win_host> [win_root]
# 範例:
#   ./sync_to_mac.sh robert 192.168.1.40 "F:/AI_DRAMA_FACTORY"
# ============================================================================
set -euo pipefail

WIN_USER="${1:-}"
WIN_HOST="${2:-}"
WIN_ROOT="${3:-F:/AI_DRAMA_FACTORY}"
MAC_ROOT="/Volumes/AI_Workspace/AI_DRAMA_FACTORY"

if [[ -z "$WIN_USER" || -z "$WIN_HOST" ]]; then
  echo "用法: $0 <win_user> <win_host> [win_root]" >&2
  exit 1
fi

if ! mount | grep -q "/Volumes/AI_Workspace"; then
  echo "[sync] 外接 SSD 未掛載，請先掛載 /Volumes/AI_Workspace" >&2
  exit 1
fi
mkdir -p "$MAC_ROOT"

EXCLUDES=(
  --exclude 'node_modules/'
  --exclude 'venv/'
  --exclude '.venv/'
  --exclude '__pycache__/'
  --exclude '.git/'
  --exclude 'output/'
  --exclude 'logs/'
  --exclude 'data/'
  --exclude '*.pyc'
  --exclude '.DS_Store'
)

for item in LocalMiniDrama-main Auto_Drama; do
  echo "[sync] 拉取 $item ..."
  rsync -avz --delete "${EXCLUDES[@]}" \
    "${WIN_USER}@${WIN_HOST}:${WIN_ROOT}/${item}/" \
    "${MAC_ROOT}/${item}/"
done

echo "[sync] 完成: $MAC_ROOT"
