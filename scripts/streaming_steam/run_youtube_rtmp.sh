#!/usr/bin/env bash
# 以 concat + copy 推一路 YouTube RTMP；外層在 ffmpeg 退出時自動重啟（網路瞬斷、程序崩潰）。
#
# 前置：
#   1) brew install ffmpeg   （或自編有 librtmp 之 ffmpeg）
#   2) 已執行 build_concat_playlist.sh
#   3) 建立 Streaming/secrets/rtmp.env ，內容一行：
#        export YOUTUBE_RTMP_URL='rtmp://a.rtmp.youtube.com/live2/你的金鑰'
#
# 用法：
#   export STREAMING_ROOT="/Volumes/AI_Workspace/AI_Drama_Factory/Streaming"
#   （相容：STEAM_ROOT）
#   ./run_youtube_rtmp.sh
#
# 建議：tmux new -s rs_live → 在 session 裡跑本腳本；Mac 上可再加 launchd 開機自啟 tmux（略）。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STREAMING_ROOT="${STREAMING_ROOT:-${STEAM_ROOT:-${REPO_ROOT}/Streaming}}"
ENV_FILE="${STREAMING_ROOT}/secrets/rtmp.env"
PLAYLIST="${STREAMING_ROOT}/config/concat_playlist.txt"

# 非互動 session（SSH/launchd）常缺 PATH，這裡先補齊常見路徑
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

# 優先使用固定路徑，避免 launchd 找不到 ffmpeg
if [[ -x "/opt/homebrew/bin/ffmpeg" ]]; then
  FFMPEG_BIN="/opt/homebrew/bin/ffmpeg"
elif [[ -x "/usr/local/bin/ffmpeg" ]]; then
  FFMPEG_BIN="/usr/local/bin/ffmpeg"
elif command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG_BIN="$(command -v ffmpeg)"
else
  echo "❌ 找不到 ffmpeg（請先安裝：brew install ffmpeg）" >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "❌ 找不到 ${ENV_FILE}" >&2
  echo "   請建立並填入：export YOUTUBE_RTMP_URL='rtmp://...'" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${ENV_FILE}"

if [[ -z "${YOUTUBE_RTMP_URL:-}" ]]; then
  echo "❌ YOUTUBE_RTMP_URL 未設定" >&2
  exit 1
fi

if [[ ! -f "${PLAYLIST}" ]]; then
  echo "❌ 找不到 ${PLAYLIST} ，請先執行 build_concat_playlist.sh" >&2
  exit 1
fi

LOG_DIR="${STREAMING_ROOT}/logs"
mkdir -p "${LOG_DIR}"
cd "${STREAMING_ROOT}/config"

echo "▶ Streaming 根目錄：${STREAMING_ROOT}"
echo "▶ Playlist：${PLAYLIST}"
echo "▶ FFmpeg：${FFMPEG_BIN}"
echo "▶ 按 Ctrl+C 結束；若 ffmpeg 退出將於 5 秒後重試…"

while true; do
  ts="$(date +%Y%m%d_%H%M%S)"
  log="${LOG_DIR}/ffmpeg_${ts}.log"
  echo "—— 開始 ffmpeg @ ${ts} ——" | tee -a "${log}"
  set +e
  "${FFMPEG_BIN}" -hide_banner -loglevel info -nostdin \
    -re -f concat -safe 0 -stream_loop -1 \
    -i "concat_playlist.txt" \
    -c:v copy -c:a copy \
    -f flv "${YOUTUBE_RTMP_URL}" \
    2>&1 | tee -a "${log}"
  code=$?
  set -e
  echo "—— ffmpeg 結束 exit=${code} @ $(date "+%Y-%m-%d %H:%M:%S") ——" | tee -a "${log}"
  sleep 5
done

