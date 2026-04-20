#!/usr/bin/env bash
# 產生 FFmpeg concat demuxer 用清單（路徑相對於 playlist 所在目錄）。
#
# 優先順序（opt-in manifest）：
#   1) 若存在 $STEAM_ROOT/config/live_manifest.json → 呼叫 emit_concat_from_manifest.py
#   2) 否則若存在 $STEAM_ROOT/queue/order.txt → 依檔名列表
#   3) 否則依 queue/*.mp4 檔名字串排序
#
# 用法：
#   export STREAMING_ROOT="/Volumes/AI_Workspace/AI_Drama_Factory/Streaming"
#   （相容舊名：STEAM_ROOT 仍可用）
#   ./build_concat_playlist.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
STREAMING_ROOT="${STREAMING_ROOT:-${STEAM_ROOT:-${REPO_ROOT}/Streaming}}"
QUEUE="${STREAMING_ROOT}/queue"
CONFIG="${STREAMING_ROOT}/config"
OUT="${CONFIG}/concat_playlist.txt"
ORDER_FILE="${QUEUE}/order.txt"
MANIFEST="${CONFIG}/live_manifest.json"
EMIT_PY="${SCRIPT_DIR}/emit_concat_from_manifest.py"

if [[ ! -d "${QUEUE}" ]]; then
  echo "❌ 找不到 queue 目錄：${QUEUE}" >&2
  echo "   請建立 Streaming/queue 並放入 1hr MP4。" >&2
  exit 1
fi

mkdir -p "${CONFIG}"

tmp="$(mktemp)"
cleanup() { rm -f "${tmp}"; }
trap cleanup EXIT

if [[ -f "${MANIFEST}" ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ 使用 live_manifest.json 需要 python3" >&2
    exit 1
  fi
  python3 "${EMIT_PY}" --streaming-root "${STREAMING_ROOT}" --manifest "${MANIFEST}" > "${tmp}"
  echo "ℹ️  已使用 manifest：${MANIFEST}"
elif [[ -f "${ORDER_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
    base="$(basename "${line}")"
    f="${QUEUE}/${base}"
    if [[ ! -f "${f}" ]]; then
      echo "❌ order.txt 列了不存在的檔：${base}" >&2
      exit 1
    fi
    printf "file '../queue/%s'\n" "${base}" >> "${tmp}"
  done < "${ORDER_FILE}"
  echo "ℹ️  已使用 order.txt：${ORDER_FILE}"
else
  shopt -s nullglob
  files=( "${QUEUE}"/*.mp4 )
  if [[ ${#files[@]} -eq 0 ]]; then
    echo "❌ ${QUEUE} 內沒有任何 .mp4" >&2
    exit 1
  fi
  IFS=$'\n' sorted=( $(printf '%s\n' "${files[@]}" | sort) )
  unset IFS
  for f in "${sorted[@]}"; do
    printf "file '../queue/%s'\n" "$(basename "${f}")" >> "${tmp}"
  done
  echo "ℹ️  已依檔名排序掃描 ${QUEUE}/*.mp4"
fi

mv "${tmp}" "${OUT}"
trap - EXIT
echo "✅ 已寫入 ${OUT}（$(grep -c ^file "${OUT}" || true) 條 file）"

