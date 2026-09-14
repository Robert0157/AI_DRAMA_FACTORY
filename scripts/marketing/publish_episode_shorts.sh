#!/bin/bash
# Upload ONE video-native episode bundle (oldest first) from
# Shorts_Queue/<channel>/episodes/*.episode.json via porjo/youtubeuploader.
#
# Fail-closed: on any failure the bundle stays in place and the script exits
# non-zero. On success the mp4 + sidecar move to episodes/_uploaded/ and one
# line is appended to Shorts_Queue/<channel>/upload_history.jsonl (same shape
# the distribution ledger reads).
#
# Usage: bash scripts/marketing/publish_episode_shorts.sh [--dry-run]
#   EPISODE_CHANNEL=lofi|light_music   (default: lofi)
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

MARKETING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${MARKETING_DIR}/../.." && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"
export TZ="${EPISODE_SCHEDULE_TZ:-Asia/Taipei}"

CHANNEL="${EPISODE_CHANNEL:-lofi}"
EP_DIR="${REPO_ROOT}/Shorts_Queue/${CHANNEL}/episodes"
UPLOADED_DIR="${EP_DIR}/_uploaded"
HISTORY_JSONL="${REPO_ROOT}/Shorts_Queue/${CHANNEL}/upload_history.jsonl"
UPLOADER_BIN="${UPLOADER_BIN:-${MARKETING_DIR}/youtubeuploader}"
LOCAL_OAUTH_DIR="${SHORTS_LOCAL_OAUTH_DIR:-${HOME}/Library/Application Support/AI_Drama_Factory/shorts_youtube_oauth}"
TG_SEND_PY="${REPO_ROOT}/scripts/telegram/telegram_text_send.py"
TG_ENV_DEFAULT="${HOME}/Library/Application Support/AI_Drama_Factory/telegram_queue_notify.env"
RETRY_MAX="${EPISODE_UPLOAD_RETRY_MAX:-3}"
RETRY_SLEEP="${EPISODE_UPLOAD_RETRY_SLEEP_SEC:-10}"

tg_notify() {
  [[ -f "${TG_SEND_PY}" ]] || return 0
  local _tg_env="${TELEGRAM_ENV_FILE:-}"
  [[ -z "${_tg_env}" && -f "${TG_ENV_DEFAULT}" ]] && _tg_env="${TG_ENV_DEFAULT}"
  AI_DRAMA_REPO_ROOT="${REPO_ROOT}" \
    TELEGRAM_ENV_FILE="${_tg_env}" \
    /usr/bin/env python3 "${TG_SEND_PY}" "$1" >/dev/null 2>&1 || true
}

[[ -x "${UPLOADER_BIN}" ]] || { echo "❌ 找不到 ${UPLOADER_BIN}"; exit 1; }

# FIFO pick: oldest sidecar first (ls -tr).
SIDECAR="$(ls -1tr "${EP_DIR}"/*.episode.json 2>/dev/null | head -1 || true)"
if [[ -z "${SIDECAR}" ]]; then
  echo "ℹ 無待上傳節目包（${EP_DIR}）"
  exit 0
fi

# Resolve the video file referenced by the sidecar.
VIDEO_NAME="$(/usr/bin/env python3 - "${SIDECAR}" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("video_file", ""))
PY
)"
if [[ -z "${VIDEO_NAME}" || ! -f "${EP_DIR}/${VIDEO_NAME}" ]]; then
  echo "❌ sidecar 指向的影片不存在：${EP_DIR}/${VIDEO_NAME}" >&2
  exit 1
fi

PRIVACY="$(/usr/bin/env python3 - "${SIDECAR}" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8")).get("privacy", "unlisted"))
PY
)"

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "[dry-run] 將上傳：${EP_DIR}/${VIDEO_NAME}（privacy=${PRIVACY}）"
  exit 0
fi

# Local staging (launchd cannot reliably reach /Volumes for OAuth files).
mkdir -p "${LOCAL_OAUTH_DIR}"
for f in client_secrets.json request.token; do
  [[ -f "${MARKETING_DIR}/${f}" ]] && cp -f "${MARKETING_DIR}/${f}" "${LOCAL_OAUTH_DIR}/${f}"
done

# Build porjo metaJSON from the episode sidecar.
META_JSON="$(mktemp -t episode_meta_XXXXXX.json)"
/usr/bin/env python3 - "${SIDECAR}" "${META_JSON}" <<'PY'
import json, sys
body = json.load(open(sys.argv[1], encoding="utf-8"))
meta = {
    "title": body.get("title", ""),
    "description": body.get("description", ""),
    "tags": body.get("tags", []),
    "categoryId": "10",
    "privacyStatus": body.get("privacy", "unlisted"),
    "madeForKids": bool(body.get("selfDeclaredMadeForKids", False)),
    "containsSyntheticMedia": bool(body.get("containsSyntheticMedia", True)),
}
json.dump(meta, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY

echo "▶ 上傳 ${VIDEO_NAME}（${CHANNEL}, privacy=${PRIVACY}）"
UPLOAD_OUT=""
for attempt in $(seq 1 "${RETRY_MAX}"); do
  if UPLOAD_OUT="$("${UPLOADER_BIN}" \
      -filename "${EP_DIR}/${VIDEO_NAME}" \
      -secrets "${LOCAL_OAUTH_DIR}/client_secrets.json" \
      -cache "${LOCAL_OAUTH_DIR}/request.token" \
      -metaJSON "${META_JSON}" 2>&1)"; then
    break
  fi
  echo "⚠ 第 ${attempt}/${RETRY_MAX} 次失敗，${RETRY_SLEEP}s 後重試" >&2
  echo "${UPLOAD_OUT}" >&2
  [[ "${attempt}" == "${RETRY_MAX}" ]] && { rm -f "${META_JSON}"; exit 1; }
  sleep "${RETRY_SLEEP}"
done
rm -f "${META_JSON}"

VIDEO_ID="$(printf '%s' "${UPLOAD_OUT}" | sed -n 's/.*[Vv]ideo [Ii][Dd][: ]*\([A-Za-z0-9_-]\{6,\}\).*/\1/p' | head -1)"

# Mirror the refreshed OAuth token back to the repo copy (same as publish_shorts.sh).
[[ -f "${LOCAL_OAUTH_DIR}/request.token" ]] && cp -f "${LOCAL_OAUTH_DIR}/request.token" "${MARKETING_DIR}/request.token" || true

mkdir -p "${UPLOADED_DIR}"
mv -f "${EP_DIR}/${VIDEO_NAME}" "${UPLOADED_DIR}/${VIDEO_NAME}"
ARCHIVED_SIDECAR="${UPLOADED_DIR}/$(basename "${SIDECAR}")"
mv -f "${SIDECAR}" "${ARCHIVED_SIDECAR}"

/usr/bin/env python3 - "${HISTORY_JSONL}" "${VIDEO_ID}" "${VIDEO_NAME}" "${ARCHIVED_SIDECAR}" "${CHANNEL}" <<'PY'
import json, sys
from datetime import datetime, timedelta, timezone
history, video_id, video_name, sidecar_path, channel = sys.argv[1:6]
try:
    body = json.load(open(sidecar_path, encoding="utf-8"))
except Exception:
    body = {}
tz_tpe = timezone(timedelta(hours=8))
record = {
    "ts": datetime.now(tz_tpe).strftime("%Y-%m-%dT%H:%M:%S%z"),
    "status": "success",
    "video_id": video_id,
    "file": video_name,
    "title": body.get("title", ""),
    "description": body.get("description", ""),
    "metadata_mode": "episode",
    "channel": channel,
}
with open(history, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
print(f"HISTORY appended -> {history}")
PY

tg_notify "[節目上傳] ${CHANNEL}｜$(basename "${VIDEO_NAME}")｜video_id=${VIDEO_ID:-unknown}｜privacy=${PRIVACY}"
echo "✅ 上傳完成 video_id=${VIDEO_ID:-unknown}"
