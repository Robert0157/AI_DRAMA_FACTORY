#!/bin/bash
# ============================================================================
# deploy_mac_phase1.sh
# v15.10 Mac mini 二階段部署自動化驗證 (P2-#10)
#
# 用途: 在 Mac mini 上執行 Phase 1 部署預檢，確保 Streaming/ 環境就緒
# 使用: bash deploy_mac_phase1.sh [--verify-only]
#
# Phase 1: 24/7 直播營運節點 (OBS/RTMP + Streaming/ runtime)
# Phase 2: 全自動化主機 (待 Phase 1 穩定後遷移)
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STREAMING_ROOT="${STREAMING_ROOT:-/Volumes/AI_Workspace/AI_Drama_Factory/Streaming}"
VERIFY_ONLY=false

# 顏色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "${GREEN}  ✅ $1${NC}"; }
fail() { echo -e "${RED}  ❌ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
info() { echo -e "${CYAN}  ℹ️  $1${NC}"; }

# ============================================================================
# 1. 先決條件檢查
# ============================================================================

verify_prerequisites() {
    echo ""
    echo "🔍 [1/5] 先決條件檢查..."

    local missing=0

    # ffmpeg
    if command -v ffmpeg &>/dev/null; then
        local ff_ver=$(ffmpeg -version 2>&1 | head -1)
        pass "ffmpeg: $ff_ver"
    else
        fail "ffmpeg 未安裝 → brew install ffmpeg"
        missing=$((missing + 1))
    fi

    # ffprobe
    if command -v ffprobe &>/dev/null; then
        pass "ffprobe 已安裝"
    else
        fail "ffprobe 未安裝 (隨 ffmpeg 安裝)"
        missing=$((missing + 1))
    fi

    # python3
    if command -v python3 &>/dev/null; then
        local py_ver=$(python3 --version 2>&1)
        pass "python3: $py_ver"
    else
        fail "python3 未安裝"
        missing=$((missing + 1))
    fi

    # git
    if command -v git &>/dev/null; then
        pass "git 已安裝"
    else
        warn "git 未安裝 (可選)"
    fi

    # OBS (optional)
    if [ -d "/Applications/OBS.app" ]; then
        pass "OBS.app 已安裝"
    else
        warn "OBS.app 未安裝 (RTMP 直播需手動啟動 OBS)"
    fi

    if [ $missing -gt 0 ]; then
        echo ""
        echo -e "${RED}❌ $missing 項先決條件缺失，請安裝後重試${NC}"
        exit 1
    fi
}

# ============================================================================
# 2. 外接硬碟檢查
# ============================================================================

verify_mount() {
    echo ""
    echo "🔍 [2/5] 外接硬碟掛載檢查..."

    if mount | grep -q "/Volumes/AI_Workspace"; then
        pass "AI_Workspace 已掛載"
    else
        fail "AI_Workspace 未掛載 → 請插入外接 SSD"
        echo "   預期掛載點: /Volumes/AI_Workspace"
        exit 1
    fi

    # 檢查可用空間
    local avail=$(df -h /Volumes/AI_Workspace | tail -1 | awk '{print $4}')
    info "可用空間: $avail"
}

# ============================================================================
# 3. Streaming 目錄結構初始化
# ============================================================================

setup_streaming_root() {
    echo ""
    echo "🔍 [3/5] Streaming 目錄結構..."

    local dirs=(
        "$STREAMING_ROOT/queue"
        "$STREAMING_ROOT/queue_staging"
        "$STREAMING_ROOT/config"
        "$STREAMING_ROOT/secrets"
        "$STREAMING_ROOT/logs"
        "$STREAMING_ROOT/frozen_broadcast"
    )

    local created=0
    for d in "${dirs[@]}"; do
        if [ ! -d "$d" ]; then
            mkdir -p "$d"
            created=$((created + 1))
            info "建立: $d"
        fi
    done

    if [ $created -gt 0 ]; then
        pass "已建立 $created 個目錄"
    else
        pass "所有目錄已存在"
    fi
}

# ============================================================================
# 4. Manifest 驗證
# ============================================================================

verify_manifest() {
    echo ""
    echo "🔍 [4/5] Manifest 驗證..."

    local manifest="$STREAMING_ROOT/config/live_manifest.json"

    if [ ! -f "$manifest" ]; then
        # 建立範本
        local example="$SCRIPT_DIR/streaming_steam/live_manifest.example.json"
        if [ -f "$example" ]; then
            cp "$example" "$manifest"
            warn "已建立範本 manifest.json，請手動編輯 slot 檔名"
        else
            fail "找不到 live_manifest.example.json"
            exit 1
        fi
    fi

    # 驗證 JSON 格式
    if python3 -c "import json; json.load(open('$manifest'))" 2>/dev/null; then
        pass "manifest.json JSON 格式有效"

        # 檢查 slots
        local slot_count=$(python3 -c "
import json
data = json.load(open('$manifest'))
print(len(data.get('slots', [])))
" 2>/dev/null || echo "0")
        info "已註冊 $slot_count 個 slot"
    else
        fail "manifest.json JSON 格式無效"
        exit 1
    fi
}

# ============================================================================
# 5. Concat 播放清單測試
# ============================================================================

test_concat() {
    echo ""
    echo "🔍 [5/5] Concat 播放清單測試..."

    local build_script="$SCRIPT_DIR/streaming_steam/build_concat_playlist.sh"

    if [ ! -f "$build_script" ]; then
        warn "build_concat_playlist.sh 不存在，跳過 concat 測試"
        return
    fi

    if [ "$VERIFY_ONLY" = true ]; then
        info "驗證模式：跳過實際 concat 建構"
        return
    fi

    # 檢查是否有 MP4 在 queue/
    local mp4_count=$(find "$STREAMING_ROOT/queue" -name "*.mp4" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$mp4_count" -eq 0 ]; then
        warn "queue/ 無 MP4 檔案，跳過 concat 測試"
        return
    fi

    info "queue/ 中有 $mp4_count 個 MP4，執行 concat..."
    bash "$build_script" && pass "Concat 建構成功" || fail "Concat 建構失敗"
}

# ============================================================================
# Main
# ============================================================================

main() {
    echo ""
    echo "=============================================="
    echo "🚀 Mac mini Phase 1 部署預檢 v15.10"
    echo "=============================================="
    echo "  目標: $STREAMING_ROOT"
    echo "  模式: $([ "$VERIFY_ONLY" = true ] && echo '驗證' || echo '完整')"
    echo ""

    verify_prerequisites
    verify_mount
    setup_streaming_root
    verify_manifest
    test_concat

    echo ""
    echo "=============================================="
    echo -e "${GREEN}🎉 Phase 1 預檢完成！Mac mini 已準備就緒${NC}"
    echo "=============================================="
    echo ""
    echo "下一步："
    echo "  1. 編輯 config/live_manifest.json 設定 slot"
    echo "  2. bash run_youtube_rtmp.sh 啟動 RTMP 直播"
    echo "  3. 開啟 OBS → 設定 Media Source → 指向 concat 輸出"
}

# 參數解析
while [[ $# -gt 0 ]]; do
    case $1 in
        --verify-only)
            VERIFY_ONLY=true
            shift
            ;;
        --streaming-root)
            STREAMING_ROOT="$2"
            shift 2
            ;;
        *)
            echo "未知參數: $1"
            echo "用法: $0 [--verify-only] [--streaming-root /path/to/Streaming]"
            exit 1
            ;;
    esac
done

main
