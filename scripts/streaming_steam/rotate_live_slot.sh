#!/usr/bin/env bash
# 輪換一個直播槽位（只動 manifest + mv；實作在 rotate_live_manifest.py）。
#
# 規則：固定替換 **added_at 最小** 的那一筆；若同分則 **slot 較小** 者。
#
# 前置：
#   - Streaming/config/live_manifest.json 已存在，且每筆 entries 皆有 added_at（ISO-8601）
#   - 新歌已置於 Streaming/queue_staging/<純檔名>
#
# 用法：
#   export STREAMING_ROOT="/Volumes/AI_Workspace/AI_Drama_Factory/Streaming"
#   （相容：STEAM_ROOT）
#   ./rotate_live_slot.sh my_new_hour.mp4
#   ./rotate_live_slot.sh --dry-run my_new_hour.mp4
#
# 之後請執行 build_concat_playlist.sh，並視情況重啟 ffmpeg。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STREAMING_ROOT="${STREAMING_ROOT:-${STEAM_ROOT:-${REPO_ROOT}/Streaming}}"
PY="${SCRIPT_DIR}/rotate_live_manifest.py"

DRY=()
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY=(--dry-run)
  shift
fi

if [[ -z "${1:-}" ]]; then
  echo "用法: $0 [--dry-run] <staging 內新檔純檔名.mp4>" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ 需要 python3" >&2
  exit 1
fi

exec python3 "${PY}" --streaming-root "${STREAMING_ROOT}" "${DRY[@]}" --new-file "$1"

