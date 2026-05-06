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
DOTENV_FILE="${REPO_ROOT}/.env"
PLAYLIST="${STREAMING_ROOT}/config/concat_playlist.txt"
TARGET_FPS="${TARGET_FPS:-30}"
KEYINT_SEC="${KEYINT_SEC:-2}"
X264_PRESET="${X264_PRESET:-veryfast}"
VIDEO_BITRATE="${VIDEO_BITRATE:-2500k}"
VIDEO_MAXRATE="${VIDEO_MAXRATE:-3000k}"
VIDEO_BUFSIZE="${VIDEO_BUFSIZE:-6000k}"
AUDIO_BITRATE="${AUDIO_BITRATE:-160k}"

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

read_dotenv_value() {
  local file="$1"
  local key="$2"
  [[ -f "${file}" ]] || return 1
  python3 - "${file}" "${key}" <<'PY'
import re
import sys
from pathlib import Path

file = Path(sys.argv[1])
key = sys.argv[2]
pat = re.compile(rf'^(?:export\s+)?{re.escape(key)}\s*=\s*(.+?)\s*$')
for raw in file.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    m = pat.match(line)
    if not m:
        continue
    val = m.group(1).strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    print(val)
    raise SystemExit(0)
raise SystemExit(1)
PY
}

RTMP_URL=""
if [[ -n "${YOUTUBE_RTMP_URL:-}" ]]; then
  RTMP_URL="${YOUTUBE_RTMP_URL}"
elif [[ -f "${ENV_FILE}" ]]; then
  # shellcheck source=/dev/null
  source "${ENV_FILE}"
  RTMP_URL="${YOUTUBE_RTMP_URL:-}"
fi

if [[ -z "${RTMP_URL}" ]]; then
  RTMP_URL="$(read_dotenv_value "${DOTENV_FILE}" "YOUTUBE_RTMP_URL" || true)"
fi
if [[ -z "${RTMP_URL}" ]]; then
  key="$(read_dotenv_value "${DOTENV_FILE}" "YOUTUBE_KEY" || true)"
  if [[ -n "${key}" ]]; then
    RTMP_URL="rtmp://a.rtmp.youtube.com/live2/${key}"
  fi
fi
if [[ -z "${RTMP_URL}" ]]; then
  echo "❌ 找不到可用的 RTMP 設定（YOUTUBE_RTMP_URL / YOUTUBE_KEY）" >&2
  echo "   可放在 Streaming/secrets/rtmp.env 或 repo .env" >&2
  exit 1
fi

if [[ ! -f "${PLAYLIST}" ]]; then
  echo "❌ 找不到 ${PLAYLIST} ，請先執行 build_concat_playlist.sh" >&2
  exit 1
fi

LOG_DIR="${STREAMING_ROOT}/logs"
mkdir -p "${LOG_DIR}"
cd "${STREAMING_ROOT}/config"

# 單實例鎖：避免同時啟兩個推流程序
LOCK_PARENT="${STREAMING_ROOT}/.locks"
LOCK_DIR="${LOCK_PARENT}/run_youtube_rtmp.lock"
mkdir -p "${LOCK_PARENT}"
if mkdir "${LOCK_DIR}" 2>/dev/null; then
  echo "$$" > "${LOCK_DIR}/pid"
else
  old_pid="$(cat "${LOCK_DIR}/pid" 2>/dev/null || true)"
  if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
    echo "❌ 已有推流實例在執行（pid=${old_pid}），拒絕重複啟動。" >&2
    exit 1
  fi
  echo "⚠️ 偵測到陳舊鎖，嘗試清理後重試。" >&2
  rm -rf "${LOCK_DIR}"
  mkdir "${LOCK_DIR}" 2>/dev/null || { echo "❌ 無法取得單實例鎖：${LOCK_DIR}" >&2; exit 1; }
  echo "$$" > "${LOCK_DIR}/pid"
fi

cleanup_lock() {
  rm -rf "${LOCK_DIR}" 2>/dev/null || true
}
trap cleanup_lock EXIT INT TERM

# log retention：同時按天數與檔案數限制
LOG_RETENTION_DAYS="${LOG_RETENTION_DAYS:-7}"
LOG_KEEP_MAX="${LOG_KEEP_MAX:-200}"
prune_logs() {
  find "${LOG_DIR}" -type f -name 'ffmpeg_*.log' -mtime +"${LOG_RETENTION_DAYS}" -print0 2>/dev/null \
    | xargs -0 rm -f 2>/dev/null || true

  logs=()
  while IFS= read -r line; do
    logs+=("${line}")
  done < <(ls -1t "${LOG_DIR}"/ffmpeg_*.log 2>/dev/null || true)
  if [[ "${#logs[@]}" -gt "${LOG_KEEP_MAX}" ]]; then
    for ((i=LOG_KEEP_MAX; i<${#logs[@]}; i++)); do
      rm -f "${logs[$i]}" || true
    done
  fi
}

echo "▶ Streaming 根目錄：${STREAMING_ROOT}"
echo "▶ Playlist：${PLAYLIST}"
echo "▶ FFmpeg：${FFMPEG_BIN}"
echo "▶ 單實例鎖：${LOCK_DIR}"
echo "▶ Log retention：days=${LOG_RETENTION_DAYS} keep_max=${LOG_KEEP_MAX}"
echo "▶ RTMP profile：x264 keyint<=${KEYINT_SEC}s @ ${TARGET_FPS}fps"
echo "▶ 按 Ctrl+C 結束；若 ffmpeg 退出將依退避策略重試…"

BASE_BACKOFF=5
MAX_BACKOFF=300
backoff="${BASE_BACKOFF}"

while true; do
  keyint_frames=$(( TARGET_FPS * KEYINT_SEC ))
  prune_logs
  ts="$(date +%Y%m%d_%H%M%S)"
  log="${LOG_DIR}/ffmpeg_${ts}.log"
  echo "—— 開始 ffmpeg @ ${ts} ——" | tee -a "${log}"
  set +e
  # v15.10 P3#13: STREAMING_TRANSCODE=0 → -c copy（目標已符合編碼時省 CPU，Mac mini M4 友善）
  if [[ "${STREAMING_TRANSCODE:-1}" == "0" ]]; then
    VIDEO_ENC_FLAGS=(-c:v copy -c:a copy)
  else
    VIDEO_ENC_FLAGS=(
      -c:v libx264 -preset "${X264_PRESET}" -tune zerolatency
      -pix_fmt yuv420p -r "${TARGET_FPS}"
      -g "${keyint_frames}" -keyint_min "${keyint_frames}" -sc_threshold 0
      -b:v "${VIDEO_BITRATE}" -maxrate "${VIDEO_MAXRATE}" -bufsize "${VIDEO_BUFSIZE}"
      -c:a aac -b:a "${AUDIO_BITRATE}" -ar 48000
    )
  fi
  ffmpeg_cmd=(
    "${FFMPEG_BIN}" -hide_banner -loglevel info -nostdin
    -re -fflags +genpts -f concat -safe 0 -stream_loop -1
    -i "concat_playlist.txt"
    "${VIDEO_ENC_FLAGS[@]}"
    -f flv "${RTMP_URL}"
  )
  # Mac 防休眠：阻止系統、磁碟、閒置休眠造成推流中斷
  if [[ "$(uname -s)" == "Darwin" ]] && command -v caffeinate >/dev/null 2>&1; then
    run_cmd=(caffeinate -s -m -i "${ffmpeg_cmd[@]}")
  else
    run_cmd=("${ffmpeg_cmd[@]}")
  fi
  "${run_cmd[@]}" 2>&1 | tee -a "${log}"
  code=$?
  set -e
  echo "—— ffmpeg 結束 exit=${code} @ $(date "+%Y-%m-%d %H:%M:%S") ——" | tee -a "${log}"

  echo "ℹ️  ${backoff}s 後重試…" | tee -a "${log}"
  sleep "${backoff}"
  if [[ "${code}" -eq 0 ]]; then
    backoff="${BASE_BACKOFF}"
  elif (( backoff < MAX_BACKOFF )); then
    backoff=$(( backoff * 2 ))
    if (( backoff > MAX_BACKOFF )); then
      backoff="${MAX_BACKOFF}"
    fi
  fi
done

