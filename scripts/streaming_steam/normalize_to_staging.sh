#!/usr/bin/env bash
# Ingest Gatekeeper:
# - Smart bypass: already 48k and video signature matches live queue baseline -> pass through
# - Otherwise: normalize audio only (keep video stream copy), output back to queue_staging
#
# Usage:
#   export STREAMING_ROOT="/Volumes/AI_Workspace/AI_Drama_Factory/Streaming"
#   ./scripts/streaming_steam/normalize_to_staging.sh
#   ./scripts/streaming_steam/normalize_to_staging.sh "new_file.mp4"
#
# Environment:
#   - STREAMING_ROOT (or STEAM_ROOT) optional
#   - TARGET_SAMPLE_RATE (default 48000)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STREAMING_ROOT="${STREAMING_ROOT:-${STEAM_ROOT:-${REPO_ROOT}/Streaming}}"
TARGET_SAMPLE_RATE="${TARGET_SAMPLE_RATE:-48000}"

QUEUE_DIR="${STREAMING_ROOT}/queue"
STAGING_DIR="${STREAMING_ROOT}/queue_staging"
MANIFEST="${STREAMING_ROOT}/config/live_manifest.json"
LOG_DIR="${STREAMING_ROOT}/logs"
LOG_FILE="${LOG_DIR}/ingest_gatekeeper.log"
QUARANTINE_DIR="${STAGING_DIR}/_quarantine"

mkdir -p "${LOG_DIR}" "${STAGING_DIR}" "${QUARANTINE_DIR}"

if [[ -x "/opt/homebrew/bin/ffprobe" ]]; then
  FFPROBE_BIN="/opt/homebrew/bin/ffprobe"
elif [[ -x "/usr/local/bin/ffprobe" ]]; then
  FFPROBE_BIN="/usr/local/bin/ffprobe"
elif command -v ffprobe >/dev/null 2>&1; then
  FFPROBE_BIN="$(command -v ffprobe)"
else
  echo "ERROR: ffprobe not found." >&2
  exit 1
fi

if [[ -x "/opt/homebrew/bin/ffmpeg" ]]; then
  FFMPEG_BIN="/opt/homebrew/bin/ffmpeg"
elif [[ -x "/usr/local/bin/ffmpeg" ]]; then
  FFMPEG_BIN="/usr/local/bin/ffmpeg"
elif command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG_BIN="$(command -v ffmpeg)"
else
  echo "ERROR: ffmpeg not found." >&2
  exit 1
fi

log() {
  local msg
  msg="$1"
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "${msg}" | tee -a "${LOG_FILE}"
}

probe_video_codec() {
  "${FFPROBE_BIN}" -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$1"
}

probe_video_pixfmt() {
  "${FFPROBE_BIN}" -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 "$1"
}

probe_audio_rate() {
  "${FFPROBE_BIN}" -v error -select_streams a:0 -show_entries stream=sample_rate -of csv=p=0 "$1"
}

probe_audio_channels() {
  "${FFPROBE_BIN}" -v error -select_streams a:0 -show_entries stream=channels -of csv=p=0 "$1"
}

ensure_av_present() {
  local f="$1"
  local has_v has_a
  has_v="$("${FFPROBE_BIN}" -v error -select_streams v:0 -show_entries stream=index -of csv=p=0 "${f}" || true)"
  has_a="$("${FFPROBE_BIN}" -v error -select_streams a:0 -show_entries stream=index -of csv=p=0 "${f}" || true)"
  [[ -n "${has_v}" ]] || { log "ERROR no video stream: $(basename "${f}")"; return 1; }
  [[ -n "${has_a}" ]] || { log "ERROR no audio stream: $(basename "${f}")"; return 1; }
}

find_reference_file() {
  local ref
  ref=""
  if [[ -f "${MANIFEST}" ]]; then
    ref="$(python3 - "${MANIFEST}" "${QUEUE_DIR}" <<'PY'
import json,sys
from pathlib import Path
manifest=Path(sys.argv[1])
queue=Path(sys.argv[2])
try:
    data=json.loads(manifest.read_text(encoding="utf-8-sig"))
except Exception:
    print("")
    raise SystemExit(0)
entries=data.get("entries") or []
for e in sorted(entries, key=lambda x:int(x.get("slot",0))):
    f=e.get("file")
    if isinstance(f,str) and f:
        p=queue/f
        if p.is_file():
            print(p)
            raise SystemExit(0)
print("")
PY
)"
  fi
  if [[ -z "${ref}" ]]; then
    ref="$(ls -1 "${QUEUE_DIR}"/*.mp4 2>/dev/null | head -n 1 || true)"
  fi
  echo "${ref}"
}

smart_bypass() {
  local file="$1"
  local ref="$2"
  local f_vcodec f_pix f_rate f_ch r_vcodec r_pix r_ch

  f_vcodec="$(probe_video_codec "${file}")"
  f_pix="$(probe_video_pixfmt "${file}")"
  f_rate="$(probe_audio_rate "${file}")"
  f_ch="$(probe_audio_channels "${file}")"

  if [[ -z "${ref}" ]]; then
    [[ "${f_rate}" == "${TARGET_SAMPLE_RATE}" ]]
    return
  fi

  r_vcodec="$(probe_video_codec "${ref}")"
  r_pix="$(probe_video_pixfmt "${ref}")"
  r_ch="$(probe_audio_channels "${ref}")"

  [[ "${f_rate}" == "${TARGET_SAMPLE_RATE}" && "${f_vcodec}" == "${r_vcodec}" && "${f_pix}" == "${r_pix}" && "${f_ch}" == "${r_ch}" ]]
}

normalize_audio_only() {
  local file="$1"
  local tmp
  tmp="${file%.mp4}.normtmp.mp4"

  "${FFMPEG_BIN}" -hide_banner -loglevel warning -y \
    -i "${file}" \
    -map 0:v:0 -map 0:a:0 \
    -c:v copy \
    -c:a aac -b:a 192k -ar "${TARGET_SAMPLE_RATE}" \
    "${tmp}"

  mv -f "${tmp}" "${file}"
}

process_one() {
  local file="$1"
  local ref="$2"
  local base
  base="$(basename "${file}")"

  ensure_av_present "${file}" || return 1
  if smart_bypass "${file}" "${ref}"; then
    log "BYPASS ${base}"
    return 0
  fi

  log "NORMALIZE ${base} -> audio ${TARGET_SAMPLE_RATE}Hz (video copy)"
  normalize_audio_only "${file}"
  ensure_av_present "${file}" || return 1
  if ! smart_bypass "${file}" "${ref}"; then
    log "ERROR post-normalize still incompatible: ${base}"
    return 1
  fi
  log "OK ${base}"
}

quarantine_file() {
  local file="$1"
  local base ts dest
  base="$(basename "${file}")"
  ts="$(date '+%Y%m%d_%H%M%S')"
  dest="${QUARANTINE_DIR}/${base%.mp4}_quarantine_${ts}.mp4"
  mv -f "${file}" "${dest}"
  log "QUARANTINE ${base} -> $(basename "${dest}")"
}

declare -a targets=()
if [[ $# -gt 0 ]]; then
  for arg in "$@"; do
    f="${STAGING_DIR}/$(basename "${arg}")"
    [[ -f "${f}" ]] || { log "SKIP not found: ${f}"; continue; }
    targets+=("${f}")
  done
else
  while IFS= read -r f; do
    targets+=("${f}")
  done < <(ls -1 "${STAGING_DIR}"/*.mp4 2>/dev/null || true)
fi

if [[ "${#targets[@]}" -eq 0 ]]; then
  log "No staging mp4 found."
  exit 0
fi

ref_file="$(find_reference_file)"
if [[ -n "${ref_file}" ]]; then
  log "Reference file: $(basename "${ref_file}")"
else
  log "Reference file: none (fallback: only enforce ${TARGET_SAMPLE_RATE}Hz)"
fi

ok=0
fail=0
for f in "${targets[@]}"; do
  if process_one "${f}" "${ref_file}"; then
    ok=$((ok + 1))
  else
    if [[ -f "${f}" ]]; then
      quarantine_file "${f}" || true
    fi
    fail=$((fail + 1))
  fi
done

log "Gatekeeper done: ok=${ok}, fail=${fail}, total=${#targets[@]}"
if [[ "${fail}" -gt 0 ]]; then
  exit 2
fi

