import os
import sys
import socket
import subprocess

# 強化自動尋找可用 port，遇到假閒置也能自動換 port
def _find_and_launch_streamlit(start=8601, end=8699):
    for port in range(start, end + 1):
        # 先用 socket 檢查
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) == 0:
                continue  # 已被佔用
        # 用 subprocess 啟動測試
        env = os.environ.copy()
        env["STREAMLIT_SERVER_PORT_AUTO"] = "1"
        cmd = [sys.executable, "-m", "streamlit", "run", __file__, "--server.port", str(port)]
        print(f"嘗試啟動 Streamlit 於 port {port} ...")
        proc = subprocess.Popen(cmd, env=env)
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        if proc.poll() is None:
            # 啟動成功，主程序結束
            sys.exit(0)
        # 若失敗，繼續下一個 port
    raise RuntimeError("No free port found in range.")

if __name__ == "__main__" and os.environ.get("STREAMLIT_SERVER_PORT_AUTO") != "1":
    _find_and_launch_streamlit()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【v15.10】CEO 戰略中控台 — Streamlit 六頁籤總指揮台（架構說明書_v15.10 §4.1 對齊）
"""
import html
import streamlit as st
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config
from scripts.ui.backend import get_ui_backend
from scripts.marketing.generate_shorts_pool import STYLE_CONFIG as _SHORTS_STYLE_CONFIG, CONTAINER_SOURCE_MAP as _LOFI_CONTAINER_SOURCES

st.set_page_config(page_title="R&S Echoes CEO Console", layout="wide")

if "backend" not in st.session_state:
    st.session_state.backend = get_ui_backend()

_pol = getattr(config, "freshness_policy", {}) or {}
if "ttapi_fill_fresh" not in st.session_state:
    st.session_state.ttapi_fill_fresh = bool(_pol.get("ttapi_fill_enabled", False))

# 產線 log 尾端顯示行數（與 fragment 刷新間隔配合）
_PIPELINE_LOG_TAIL_LINES = 120


def _format_pipeline_log_display(raw: str, max_lines: int) -> str:
    """等寬行號 + 分隔符，便於對齊閱讀與複製。"""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
        head = f"…（以下為檔尾最後 {max_lines} 行；完整檔請用「下載 .log」）\n\n"
    else:
        head = ""
    body = "\n".join(f"{i + 1:5d}  │  {line}" for i, line in enumerate(lines))
    return head + body


@st.fragment(run_every=1.25)
def _background_worker_pulse() -> None:
    """輪詢背景任務完成；忙碌時於主內容區顯示格式化 log（st.code 內建複製鈕）。"""
    b = st.session_state.backend
    done = b.poll_background()
    if done is not None:
        st.session_state["_pending_bg_notify"] = done
        st.rerun()

    job = b.get_background_job_status()
    log_path = b.get_active_log_path()
    if not job.get("busy"):
        return

    # 右上角輕量狀態：時鐘指針旋轉＝背景製作中
    st.markdown(
        """
<style>
@keyframes rs-bg-clock-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.rs-echoes-bg-worker-wrap {
  position: fixed; top: 0.55rem; right: 0.75rem; z-index: 10000000;
  display: flex; align-items: center; gap: 0.45rem;
  padding: 0.28rem 0.75rem; border-radius: 999px;
  background: rgba(255,255,255,0.96); border: 1px solid rgba(0,0,0,0.08);
  box-shadow: 0 2px 12px rgba(0,0,0,0.12);
  font-size: 0.75rem; font-weight: 600; color: #137333;
  pointer-events: none;
}
.rs-bg-clock-svg { width: 22px; height: 22px; flex-shrink: 0; color: #137333; }
.rs-bg-clock-hand {
  transform-origin: 0 0;
  animation: rs-bg-clock-spin 2s linear infinite;
}
</style>
<div class="rs-echoes-bg-worker-wrap" title="背景製作中（時鐘運轉中）">
  <svg class="rs-bg-clock-svg" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
    <circle cx="16" cy="16" r="13" fill="none" stroke="currentColor" stroke-width="1.6"/>
    <circle cx="16" cy="16" r="1.4" fill="currentColor"/>
    <g transform="translate(16,16)">
      <line class="rs-bg-clock-hand" x1="0" y1="0" x2="0" y2="-8"
            stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </g>
  </svg>
  <span>背景製作中…</span>
</div>
        """,
        unsafe_allow_html=True,
    )

    lbl = str(job.get("label") or "背景任務")
    with st.container(border=True):
        st.markdown(
            f"### 📟 產線即時日誌  \n"
            f"<span style='color:#5f6368;font-size:0.9rem'>**任務：** {html.escape(lbl)}  ·  "
            f"約每 1.25 秒自動刷新  ·  "
            f"使用下方程式碼區塊右上角 **複製** 即可複製全文</span>",
            unsafe_allow_html=True,
        )
        if log_path:
            lp = Path(log_path)
            tail = b.get_latest_log_lines(str(log_path), _PIPELINE_LOG_TAIL_LINES)
            display = _format_pipeline_log_display(tail, _PIPELINE_LOG_TAIL_LINES)
            st.code(display, language="text", line_numbers=False)
            p1, p2, p3 = st.columns([2, 2, 3])
            with p1:
                st.caption(f"📂 `{lp}`")
            with p2:
                try:
                    if lp.is_file():
                        st.download_button(
                            label="⬇️ 下載完整 .log",
                            data=lp.read_bytes(),
                            file_name=lp.name,
                            mime="text/plain; charset=utf-8",
                            key="dl_pipeline_log_full",
                        )
                except OSError:
                    st.caption("（完整檔讀取中…）")
            with p3:
                st.caption("提示：若畫面未更新，請稍候數秒或捲動程式碼區塊。")
        else:
            st.info("子程序啟動中… 日誌檔將寫入 `assets/.logs/`，請稍候。")


# ─────────────────────────────────────────────────────────────────
# 側邊欄（§4.1：頻道 + 聽覺／視覺衍生預覽）
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎛️ 總指揮部")
    cur_ch = st.radio(
        "當前戰區",
        options=["lofi", "light_music"],
        format_func=lambda x: "🌙 Lofi (有人物)" if x == "lofi" else "☀️ Light Music (風景)",
    )
    st.session_state.backend.set_channel(cur_ch)
    st.divider()

    st.caption("🎵 聽覺重複上限（預覽入池／退役）")
    max_audio_deriv = st.number_input("歌曲最大衍生層級 (dc)", 1, 3, 3, help="與全專案 --max-derivation-limit 預設 3 對齊")
    st.session_state.max_audio_deriv = max_audio_deriv
    ap = st.session_state.backend.get_audio_deriv_preview(max_audio_deriv)
    st.metric("聽覺 · 可入池", f"{ap['included']} 首", delta=f"退役 {ap['excluded']} 首")

    st.divider()
    st.caption("🎬 視覺重複上限（幻影輪播抽樣）")
    st.session_state.visual_max_limit = st.number_input("影片最大重複次數", 1, 10, 3)
    vp = st.session_state.backend.get_visual_deriv_preview(int(st.session_state.visual_max_limit))
    st.metric("視覺 · 可入池", f"{vp['included']} 支", delta=f"退役 {vp['excluded']} 支")

# ─────────────────────────────────────────────────────────────────
# 抬頭：全站狀態
# ─────────────────────────────────────────────────────────────────
try:
    ch_info = st.session_state.backend.get_channel_info()
    lib_stats = st.session_state.backend.get_library_stats()
except Exception as e:
    st.error(f"❌ 核心連線失敗: {e}")
    st.stop()

st.title(f"🚀 {ch_info['display_name']} — v15.9 新鮮度鐵律 · CEO 樞紐")
c1, c2, c3 = st.columns(3)
c1.metric("待處理單曲 (CEO 區)", f"{lib_stats['approved_count']} 首")
c2.metric("金庫就緒 (vault)", f"{lib_stats['vault_count']} 首")
c3.metric("戰區", ch_info["display_name"], delta=ch_info["icon"])
st.divider()

# 背景產線：輪詢 + 主版面格式化 log（須在分頁之前，才能顯示在頁面上方）
_background_worker_pulse()

# 背景任務完成回報（由 _background_worker_pulse 輪詢後寫入 _pending_bg_notify 再 rerun）
if "_pending_bg_notify" in st.session_state:
    _bg_done = st.session_state.pop("_pending_bg_notify")
    _lbl = _bg_done.get("label", "")
    if _bg_done["ok"]:
        st.success(f"背景任務完成 — {_lbl}\n{_bg_done['msg']}")
        # 與 backend.start_full_pipeline 的 label「CEO 全自動產線 ({ch})」對齊。
        # 使用遞增 nonce（非單一 bool）：Streamlit 每輪會跑完所有 tab 區塊，若在 Tab5 才 pop 會被「未切到 Tab5」時提前耗盡。
        if _lbl.startswith("CEO 全自動產線"):
            st.session_state["_pipeline_celebration_nonce"] = int(
                st.session_state.get("_pipeline_celebration_nonce", 0)
            ) + 1
    else:
        st.error(f"背景任務失敗 — {_lbl}\n{_bg_done['msg']}")

# ─────────────────────────────────────────────────────────────────
# 六頁籤（白皮書 Tab1〜Tab6）
# ─────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    [
        "📊 資產與金庫",
        "🧠 供彈",
        "📦 母帶處理",
        "🎬 影音發行流水線",
        "🚀 CEO 全自動產線",
        "🛡️ 系統維護",
    ]
)

# Tab1 — 資產入庫與金庫儀表板 + v15.9 新鮮度儀表卡
with tab1:
    st.header("📊 資產入庫與金庫儀表板")
    fr = st.session_state.backend.get_freshness_quota_report(quiet=True)
    fcol1, fcol2, fcol3 = st.columns(3)
    _icon = "✅" if fr["passed"] else ("⚠️" if fr["enforcement"] == "warn" else "❌")
    fcol1.metric(
        "新鮮度 (dc=0 可選 / 需求)",
        f"{fr['available_new']} / {fr['quota_new']} {_icon}",
        delta=f"{fr['min_ratio']*100:.0f}% 門檻 · {fr['target_tracks']} 首混音目標",
    )
    fcol2.metric("可選新歌（實體+基因）", fr["available_new"], delta=f"DB dc=0 列 {fr['available_new_raw']}")
    fcol3.metric("缺口（deficit）", fr["deficit"] if not fr["passed"] else 0)
    if fr["available_new_raw"] != fr["available_new"]:
        st.caption("可選新歌與 DB 列數不同時，表示有檔案缺失或同源排斥，與 Phase 4 閘門一致。")

    inv = st.session_state.backend.get_dual_channel_inventory()
    st.subheader("雙頻道庫存快照")
    st.dataframe(
        [
            {
                "頻道": k,
                "CEO 區曲目": v["ceo_tracks"],
                "Vault WAV": v["vault_wav"],
                "Vault ≥10?": "✅" if v["vault_ok"] else "❌",
            }
            for k, v in inv.items()
        ],
        hide_index=True,
        width="stretch",
    )

with tab2:
    st.header("🧠 企劃大腦供彈（Protocol A）")
    st.caption(
        "架構說明書 v15.10 §4.1 / spec：三引擎路由、可調組數（預設 5）、"
        "MiniMax 大量批次建議改智譜；背景執行 + assets/.logs 即時日誌。"
    )

    prov_labels = {
        "minimax": "MiniMax M2.7（NVIDIA NIM，~100s/組）",
        "zhipu": "智譜 GLM-4（~5–10s/組，批量首選）",
        "gemini": "Gemini 2.5 Flash（~15–30s/組）",
    }
    provider = st.selectbox(
        "LLM 引擎（--provider）",
        ["minimax", "zhipu", "gemini"],
        index=0,
        format_func=lambda k: prov_labels[k],
        help="與 llm_client / generate_ceo_prompts.py 一致：預設為 MiniMax M2.7（NVIDIA NIM）；大量批次可改智譜。",
    )

    # 子風格基因庫選擇（lofi 專用）
    _ceo_gene_pool: str | None = None
    _cur_ch_tab2 = st.session_state.backend.current_channel
    if _cur_ch_tab2 == "lofi":
        # 五種子風格，zara 為預設（第一項）；所有選項皆觸發容器覆寫
        # 鐵律：GL_4M_Suno_prompt.md 只能作為目標，來源由 CONTAINER_SOURCE_MAP 決定
        _lofi_sub_styles = {
            k: (_SHORTS_STYLE_CONFIG[k]["label"] + (" ★ 預設" if k == "zara" else ""))
            for k in ["zara", "gucci", "scifi", "jazz", "surreal", "uniqlo", "trending", "nightdrive"]
            if k in _SHORTS_STYLE_CONFIG
        }
        _ceo_style_key = st.selectbox(
            "子風格基因庫（容器切換）",
            options=list(_lofi_sub_styles.keys()),
            format_func=lambda k: _lofi_sub_styles[k],
            help="選擇後點擊供彈按鈕，後端自動將對應來源基因庫覆寫到 GL_4M_Suno_prompt.md 容器，再執行供彈。選 ZARA 預設 = 恢復 music_genes_ZARA_music.md 內容。",
        )
        _src_file = _LOFI_CONTAINER_SOURCES.get(_ceo_style_key, "")
        if _src_file:
            _ceo_gene_pool = f".openclaw/{_src_file}"
            if _ceo_style_key == "zara":
                st.info(f"🎵 恢復預設：GL_4M_Suno_prompt.md ← `{_src_file}`")
            else:
                st.info(f"🔄 切換容器：GL_4M_Suno_prompt.md ← `{_src_file}`")

    bcol1, bcol2 = st.columns(2)
    with bcol1:
        batch_size = st.number_input(
            "生成組數（--batch-size）",
            min_value=1,
            max_value=20,
            value=5,
            help="v15.4 起預設由 20 降為 5；可調 1–20。",
        )
    with bcol2:
        with st.expander("進階：Gemini 重試次數 (--max-retries)"):
            max_retries = st.number_input("max_retries", 1, 10, 3)

    # 耗時預估（架構說明書 v15.4 Tab2：MiniMax 組數 × ~100s）
    if provider == "minimax":
        est_s = int(batch_size) * 100
        st.warning(
            f"MiniMax 實測約 **100 秒/組**：{batch_size} 組預估 **{est_s // 60} 分 {est_s % 60} 秒**。大量批次請改用智譜 GLM-4。"
        )
    elif int(batch_size) > 5:
        st.info("大批量（>5 組）提示詞供彈建議優先使用 **智譜 GLM-4**（架構說明書 / project.yml 註記）。")

    busy = st.session_state.backend.background_busy()
    if busy:
        st.info(
            "⏳ 背景任務執行中。請看**頁面上方**「📟 產線即時日誌」區塊（格式化輸出、可一鍵複製）；右上角為輕量狀態。"
        )

    go = st.button(
        "🚀 生成一週份提示詞（背景執行）",
        type="primary",
        width="stretch",
        disabled=busy,
    )
    if go:
        ok, msg = st.session_state.backend.start_ceo_prompts_supply(
            provider=provider,
            batch_size=int(batch_size),
            max_retries=int(max_retries),
            gene_pool=_ceo_gene_pool,
        )
        if ok:
            st.success(msg)
        else:
            st.error(msg)

    if busy and st.session_state.backend.get_active_log_path():
        st.caption("💡 供彈執行中 — 即時日誌見**頁面上方**「📟 產線即時日誌」區塊（約每 1.25 秒自動刷新）。")

    # 任務完成後：在 Tab2 直接顯示完整結果 log（不再要求 CEO 去查 assets/.logs/ 或頁首）
    _last_log = st.session_state.backend.get_last_completed_log_path()
    if _last_log and not busy:
        st.markdown("#### 📋 供彈完整執行日誌")
        _last_tail = st.session_state.backend.get_latest_log_lines(_last_log, _PIPELINE_LOG_TAIL_LINES)
        _last_display = _format_pipeline_log_display(_last_tail, _PIPELINE_LOG_TAIL_LINES)
        st.code(_last_display, language="text", line_numbers=False)
        from pathlib import Path as _Path
        _lp = _Path(_last_log)
        _dc1, _dc2 = st.columns([3, 2])
        with _dc1:
            st.caption(f"📂 `{_lp.name}`")
        with _dc2:
            try:
                if _lp.is_file():
                    st.download_button(
                        label="⬇️ 下載完整 .log",
                        data=_lp.read_bytes(),
                        file_name=_lp.name,
                        mime="text/plain; charset=utf-8",
                        key="dl_ceo_prompts_log",
                    )
            except OSError:
                pass

    cep_dir = st.session_state.backend.get_ceo_prompts_dir()
    recent = st.session_state.backend.list_ceo_prompt_files(limit=10)
    st.subheader("📂 當前頻道提示詞輸出")
    st.caption(f"目錄：`{cep_dir}`（`daily_prompts_{cur_ch.upper()}_*.txt`）")
    if recent:
        for fn in recent:
            st.write(f"• `{fn}`")
    else:
        st.write("（尚無檔案 — 執行供彈後會寫入此目錄）")

# === Shorts 雙語標題彈藥庫生成區塊 ===
    st.divider()
    st.subheader("🎬 Shorts 雙語標題彈藥庫生成")
    st.caption(f"由 Windows 端 MiniMax 2.7 產生，根據當前戰區 **{cur_ch.upper()}** 與所選子風格寫入 `queue_staging/shorts_meta_pool_{{channel}}_{{style}}.json`，供 Mac mini 自動消耗。")

    # v15.11 子風格選單（lofi + light_music 皆支援）
    _lofi_style_labels = {
        "zara": "☕ ZARA — 商業浩室 (Minimal/Tech House)",
        "gucci": "✨ GUCCI — 前衛奢華 (Avant-Garde/Neo-Classical)",
        "scifi": "👾 SCI-FI — 科幻電子 (Synthwave/Glitch IDM)",
        "jazz": "🎷 JAZZ — 爵士酒廊 (Smooth Jazz/Cafe Bossa)",
        "surreal": "🌌 SURREAL — 超現實史詩 (Cinematic Ethereal/Dark Ambient)",
        "uniqlo": "✨ UNIQLO — LifeWear 日常美學 (ShibuyaKei/LightBossa/UpbeatAcoustic)",
        "trending": "🔥 TRENDING — 爆款病毒音樂 (Phonk/K-Pop Instrumental)",
        "nightdrive": "🌃 NIGHTDRIVE — 深夜兜風 (Emotional Deep House)",
    }
    _lm_style_labels = {
        "auto": "🔄 四風格自動輪轉 (CelticFolk→Piano→NeoClassical→Zen)",

        "celtic": "🌿 CelticFolk — 居爾特奇幻民謠",
        "piano": "🎹 PianoImpression — 印象派純鋼琴",
        "neoclassical": "🎻 NeoClassical — 新古典史詩",
        "zen": "🧘 ZenAmbient — 禪意環境聲景",
    }
    if cur_ch == "lofi":
        _style_choice = st.selectbox(
            "🎨 子風格（lofi 動態容器）",
            options=list(_lofi_style_labels.keys()),
            format_func=lambda k: _lofi_style_labels[k],
            index=0,
            help="選擇本次 Shorts 標題庫的音樂風格基因。",
        )
    else:
        _style_choice = st.selectbox(
            "🎨 子風格（light_music 四大自然矩陣）",
            options=list(_lm_style_labels.keys()),
            format_func=lambda k: _lm_style_labels[k],
            index=0,
            help="auto = 每組自動輪轉四大風格。若選單一風格則全部使用該風格。",
        )

    shorts_batch_size = st.number_input("生成 Shorts 標題組數", min_value=5, max_value=100, value=30, step=5)
    busy_shorts = st.session_state.backend.background_busy()
    go_shorts = st.button(
        "🚀 生成 Shorts 雙語標題彈藥庫（背景執行）",
        type="primary",
        disabled=busy_shorts,
        help="生成過程即時日誌已整合至頁首「📟 產線即時日誌」區塊。"
    )
    if go_shorts:
        ok, msg, log_path = st.session_state.backend.run_shorts_pool_with_log(
            int(shorts_batch_size), channel=cur_ch, sub_style=_style_choice
        )
        if ok:
            st.success(msg)
        else:
            st.error(msg)
    # 強制分頁內 log 永遠顯示（不論 busy 狀態）
    log_path = st.session_state.backend.get_active_log_path()
    if log_path:
        tail = st.session_state.backend.get_latest_log_lines(log_path, _PIPELINE_LOG_TAIL_LINES)
        display = _format_pipeline_log_display(tail, _PIPELINE_LOG_TAIL_LINES)
        st.markdown("#### 📟 Shorts 產線即時日誌（本分頁專屬）")
        st.code(display, language="text", line_numbers=False)
    else:
        st.caption("（目前無執行中任務，請啟動生成以查看即時日誌）")

with tab3:
    st.header("📦 批量母帶處理（僅 Phase 1+2）")
    st.caption(
        "僅執行：掃描 ceo_approved_beats → 母帶壓制（-16/-18 LUFS）→ 同步至 vault。\n"
        "跳過：lofi_assembler、music_metadata_engine（需再分別執行 Tab4）。"
    )
    _busy_tab3 = st.session_state.backend.background_busy()

    with st.expander("📋 一鍵檢查清單：CEO 入庫 ↔ mastered_tracks", expanded=False):
        st.caption(
            "比對規則：`sanitize_filename(檔名主幹)` 是否在 `mastered_tracks/{頻道}/` 存在 "
            "`*_YT_*.wav`。**待母帶**＝尚無對應母帶（可安全跑「啟動母帶壓制」處理）。"
        )
        if st.button("🔍 掃描並顯示（當前戰區）", type="secondary", key="btn_ceo_master_checklist", disabled=_busy_tab3):
            st.session_state["_ceo_master_cl"] = st.session_state.backend.get_ceo_approved_mastering_checklist(
                cur_ch
            )
        cl = st.session_state.get("_ceo_master_cl")
        if cl:
            p1, p2 = st.columns(2)
            p1.metric("⏳ 待母帶（尚無 _YT_*.wav）", cl["pending_count"])
            p2.metric("✅ 已有對應母帶", cl["mastered_count"])
            st.caption(f"`ceo_approved`: `{cl['beat_dir']}`  →  `mastered_tracks`: `{cl['master_dir']}`")
            if cl["pending_count"]:
                st.warning(f"以下 **{cl['pending_count']}** 個檔案仍待母帶（或母帶失敗需重跑）：")
                st.dataframe(
                    cl["pending"],
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "filename": st.column_config.TextColumn("檔名"),
                        "safe_stem": st.column_config.TextColumn("比對用 stem"),
                        "mtime": st.column_config.TextColumn("修改時間"),
                        "size_mb": st.column_config.NumberColumn("大小 MB", format="%.2f"),
                    },
                )
            else:
                st.success("✅ 目前無「待母帶」檔案（或目錄為空）。")
            with st.expander("已對應母帶明細（可摺疊）", expanded=False):
                if cl["already_mastered"]:
                    st.dataframe(cl["already_mastered"], width="stretch", hide_index=True)
                else:
                    st.caption("無。")
        else:
            st.info("點選 **掃描並顯示** 載入檢查清單。")

    if st.button("⚡ 啟動母帶壓制", type="primary", width="stretch", disabled=_busy_tab3):
        ok_m, msg_m, _log_m = st.session_state.backend.run_mastering_only()
        if ok_m:
            st.success(msg_m)
        else:
            st.error(msg_m)

with tab4:

    st.header("🎬 影音發行流水線：1 小時母帶 + 幻影輪播")
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Step 1: 🎧 縫合長軌 & 雙語企劃")
        if st.button("🔥 啟動音訊發行鏈路", type="primary", width="stretch"):
            st.session_state.backend.run_phase4_sequence(
                max_audio_deriv=int(st.session_state.get("max_audio_deriv", 3))
            )
            st.success("✅ 音訊鏈路啟動！正在產生 WAV 與雙語 Cheatsheet。")

    with col_b:
        st.subheader("Step 2: 🎬 幻影輪播 (YouTube 封裝)")
        mix_list = st.session_state.backend.get_master_tapes()
        sel = st.selectbox("選擇 1 小時母帶：", ["-- 請選擇 --"] + mix_list, key="tape_select")

        dwell_map = {900: "15 分鐘 (4支)", 600: "10 分鐘 (6支)", 300: "5 分鐘 (12支)"}
        dwell_sec = st.selectbox(
            "⏱️ 影片輪播頻率：",
            options=list(dwell_map.keys()),
            format_func=lambda x: dwell_map[x],
            index=1,
        )

        if sel != "-- 請選擇 --":
            if st.button("🎬 啟動幻影矩陣", type="primary", width="stretch"):
                audio_path = str(
                    Path(st.session_state.backend.config.workspace_root)
                    / "assets"
                    / "final_exports"
                    / cur_ch
                    / sel
                )
                st.session_state.backend.run_pipeline_proxy(
                    "multi_scene_processor.py",
                    ["--channel", cur_ch, "--audio", audio_path, "--scene-dwell-time", str(dwell_sec)],
                )
                st.success("✅ 輪播矩陣啟動！")


# Tab5 — CEO 全自動產線（Phase 1–5）+ v15.9 閘門與 TTAPI + 審核發行
with tab5:

    # 產線完成自動高亮：nonce 與「Tab5 已展示過的 nonce」比對，避免 bool 在背景 rerun 時被未顯示的 Tab5 區塊誤清
    _cele_nonce = st.session_state.get("_pipeline_celebration_nonce")
    _seen_nonce = st.session_state.get("_tab5_seen_celebration_nonce")
    highlight_review = _cele_nonce is not None and _cele_nonce != _seen_nonce
    if highlight_review:
        st.session_state["_tab5_seen_celebration_nonce"] = _cele_nonce
        st.success("🎉 全自動產線已完成！請立即進行 CEO 審核與發行。")
        if st.button("➡️ 前往審核與發行 (Tab4)", type="secondary", key="btn_goto_tab4_pipeline_done"):
            st.session_state["_active_tab"] = 3
            st.rerun()

    st.header("🚀 CEO 全自動產線 (Phase 1–5)")
    st.caption("架構說明書：strict 模式下新鮮度未達標時鎖定按鈕，除非啟用 TTAPI 自動補彈。")

    st.session_state.ttapi_fill_fresh = st.toggle(
        "🔫 啟用 TTAPI 自動補彈（--ttapi-fill-fresh，有費用）",
        value=st.session_state.ttapi_fill_fresh,
        help="dc=0 不足時由 TTAPI Suno 補齊缺口；與 pipeline_runner 行為一致。",
    )

    block, fr = st.session_state.backend.freshness_gate_blocks_full_pipeline(
        ttapi_fill_fresh=st.session_state.ttapi_fill_fresh
    )
    if block:
        st.warning(
            f"新鮮度未達標（可選 {fr['available_new']} / 需求 {fr['quota_new']}）。"
            " 請上傳新歌至 ceo_approved_beats，或啟用上方 TTAPI 補彈。"
        )

    args = ["--channel", cur_ch, "--auto-visual"]
    if st.session_state.ttapi_fill_fresh:
        args.append("--ttapi-fill-fresh")

    st.caption(
        "啟動後產線在**背景執行**（與 Tab2 供彈相同）：請看**右上角狀態**與**右下角 log 面板**即時尾端；"
        "勿僅依終端機 — 舊版若在畫面上看到即時 log，即因當時為非阻塞背景模式。"
    )

    btn = st.button(
        "🔥 啟動全自動產線",
        type="primary",
        width="stretch",
        disabled=block,
    )
    if btn:
        ok_fp, msg_fp = st.session_state.backend.start_full_pipeline(args)
        if ok_fp:
            st.success(msg_fp)
        else:
            st.error(msg_fp)

    st.divider()
    st.subheader("📝 自動檢查與發行控制台")
    if highlight_review:
        st.markdown(
            """
<span style='background: #ffe066; color: #b30000; font-size:1.2rem; padding:0.5em 1em; border-radius:8px;'>
🚨 產線已完成，請立即進行 CEO 審核與發行！
</span>
""",
            unsafe_allow_html=True,
        )
        st.balloons()
    st.markdown("""
**【發行前自動檢查機制】** 系統將自動檢驗 4 大核心檔案是否齊全（metadata、DistroKid_Sheet、youtube_sheet、1 小時 MP4），並透過 SMB（邊車模式）將影片與 sidecar 傳送至 Mac mini（`Y:/Long_Queue/{頻道}/`）。
""")

    check_res = st.session_state.backend.verify_export_files(channel=cur_ch)

    if not check_res["all_passed"]:
        miss = check_res["status"]["missing_list"]
        st.warning("⚠️ 發行檔案尚未齊全，請確認產線是否已完整執行：")
        for missing in miss:
            st.error(f"缺漏: {missing}")
    else:
        st.success("✅ 產線檢查通過：4 大核心檔案皆已齊全！")

        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "🚀 自動發行\n(傳送至 Mac mini 自動上傳)",
                type="primary",
                width="stretch",
            ):
                with st.spinner("透過 SMB 傳輸 1 小時影片與 Sidecar JSON 中，請勿關閉視窗..."):
                    pub_res = st.session_state.backend.publish_final_exports(channel=cur_ch, mode="auto")
                if pub_res["ok"]:
                    st.success(pub_res["msg"])
                    with st.expander("檢視去除 Shorts 標籤之 Metadata"):
                        st.json(pub_res["cleaned_metadata"])
                    if pub_res.get("log"):
                        st.caption(pub_res["log"])
                    if pub_res.get("mac_mini_upload_log"):
                        st.info(
                            "🚀 已將發行指令送往 Mac mini 待命中心。請前往 Mac mini 查看上傳日誌："
                            f"`{pub_res['mac_mini_upload_log']}`。"
                        )
                    if pub_res.get("mac_mini_video_id_track"):
                        st.caption(
                            "Video ID 追蹤檔（Mac 端預期路徑，由上傳器寫入）："
                            f"`{pub_res['mac_mini_video_id_track']}`"
                        )
                else:
                    st.error(pub_res["msg"])

        with col2:
            if st.button(
                "🙋‍♂️ 人工發行\n(傳送至 Mac mini，等待手動上傳)",
                type="secondary",
                width="stretch",
            ):
                with st.spinner("透過 SMB 傳輸 1 小時影片與 Sidecar JSON 中，請勿關閉視窗..."):
                    pub_res = st.session_state.backend.publish_final_exports(channel=cur_ch, mode="manual")
                if pub_res["ok"]:
                    st.success(pub_res["msg"])
                    with st.expander("檢視備用 YouTube CheatSheet (可點擊複製)"):
                        st.text_area(
                            "文案內容",
                            pub_res["cheatsheet"] or "",
                            height=300,
                        )
                    if pub_res.get("log"):
                        st.caption(pub_res["log"])
                    if pub_res.get("mac_mini_upload_log"):
                        st.info(
                            "🚀 已將發行指令送往 Mac mini 待命中心。請前往 Mac mini 查看上傳日誌："
                            f"`{pub_res['mac_mini_upload_log']}`。"
                        )
                    if pub_res.get("mac_mini_video_id_track"):
                        st.caption(
                            "Video ID 追蹤檔（Mac 端預期路徑，由上傳器寫入）："
                            f"`{pub_res['mac_mini_video_id_track']}`"
                        )
                else:
                    st.error(pub_res["msg"])

    # ── v15.12 DistroKid CSV 下載區塊 ───────────────────────────────
    st.divider()
    st.subheader("📥 DistroKid 發行報表下載 (v15.12)")

    exports = st.session_state.backend.get_final_exports()
    dk_csv_files = exports.get("dk_upload_csv", [])
    # v15.12 CEO 指定：CSV 集中路徑 ISRC_csv/{channel}/
    csv_dir = Path(st.session_state.backend.config.workspace_root) / "assets" / "final_exports" / "ISRC_csv" / cur_ch
    # 既有 DistroKid_Sheet 維持在 final_exports/{channel}/
    sheet_dir = Path(st.session_state.backend.config.workspace_root) / "assets" / "final_exports" / cur_ch

    if dk_csv_files:
        st.caption(f"🎵 頻道 **{cur_ch.upper()}** 的 DistroKid 上傳報表：")

        for csv_name in sorted(dk_csv_files, reverse=True)[:5]:  # 只顯示最近 5 份
            csv_path = csv_dir / csv_name
            if csv_path.exists():
                file_size_kb = round(csv_path.stat().st_size / 1024, 1)
                col_dl, col_info = st.columns([1, 3])
                with col_dl:
                    with open(csv_path, "rb") as f:
                        st.download_button(
                            label=f"⬇️ {csv_name}",
                            data=f,
                            file_name=csv_name,
                            mime="text/csv",
                            key=f"dl_{csv_name}",
                            help=f"下載 {csv_name}（{file_size_kb} KB）",
                        )
                with col_info:
                    st.caption(f"📄 {file_size_kb} KB  |  含曲目級欄位（ISRC 預留、AI 宣告、Content ID）")
    else:
        st.info(
            "尚無 DistroKid CSV 上傳報表。請先執行 **Tab5 全自動產線**（Phase 3.5 自動生成），"
            "或手動執行：\n\n"
            f"`python scripts/gear1_prod/distrokid_metadata_builder.py --channel {cur_ch}`"
        )

    # 也顯示既有 DistroKid_Sheet（人類可讀文案）
    dk_sheets = exports.get("dk_cheatsheet", [])
    if dk_sheets:
        with st.expander("📋 既有 DistroKid 文案報告 (DistroKid_Sheet_*.txt)"):
            for sheet_name in sorted(dk_sheets, reverse=True)[:5]:
                sheet_path = sheet_dir / sheet_name
                if sheet_path.exists():
                    st.caption(f"📝 {sheet_name}")

    # ── v15.12 ISRC 狀態儀表卡 ─────────────────────────────────────
    st.divider()
    st.subheader("🏷️ ISRC 版權註冊狀態 (v15.12)")

    isrc_status = st.session_state.backend.get_isrc_status(channel=cur_ch)
    total = isrc_status["total_gen0_tracks"]
    with_isrc = isrc_status["tracks_with_isrc"]
    without_isrc = isrc_status["tracks_without_isrc"]
    pct = isrc_status["isrc_coverage_pct"]

    col_ISRC_a, col_ISRC_b, col_ISRC_c = st.columns(3)
    with col_ISRC_a:
        st.metric("🎵 Gen0 總曲數", total)
    with col_ISRC_b:
        st.metric("✅ 已註冊 ISRC", with_isrc, delta=None if with_isrc == 0 else f"+{with_isrc}")
    with col_ISRC_c:
        st.metric("⏳ 待註冊 ISRC", without_isrc, delta=None if without_isrc == 0 else f"-{without_isrc}")

    # 進度條
    if total > 0:
        st.progress(pct / 100, text=f"ISRC 覆蓋率：{pct}%（{with_isrc}/{total}）")

    # 匯入摘要
    import_log = isrc_status.get("last_import_log")
    if import_log:
        with st.expander(f"📋 最近一次 ISRC 匯入摘要（{import_log.get('imported_at', '?')}）"):
            st.caption(f"來源 CSV：`{import_log.get('csv_source', '?')}`")
            st.caption(f"已寫入：{import_log.get('tracks_updated', 0)} 筆")
            st.caption(f"略過：{import_log.get('tracks_skipped', 0)} 筆")
            stw = import_log.get("warnings", [])
            if stw:
                st.warning("⚠️ 匯入警告：")
                for w in stw[:5]:
                    st.caption(f"• {w}")

    # 引導操作
    if without_isrc > 0 and total > 0:
        st.info(
            f"📥 尚有 **{without_isrc}** 首曲目待註冊 ISRC。\n\n"
            "營運 SOP：\n"
            f"1. 從上方「DistroKid 發行報表下載」取得最新 CSV\n"
            f"2. 在 DistroKid 完成發行，取得 ISRC 後回填至 CSV 的 `ISRC (Leave Blank)` 欄位\n"
            f"3. 將填好 ISRC 的 CSV **上傳至下方**，點擊匯入\n"
        )
    elif isrc_status["isrc_fully_imported"]:
        st.success(f"🎉 全部 **{total}** 首 Gen0 曲目已完成 ISRC 註冊！版權防護網已啟動。")

    if total == 0:
        st.caption("尚無 Gen0 曲目資料。請先執行產線生成母帶。")

    # ── v15.12 一鍵 ISRC 匯入 ─────────────────────────────────────
    st.divider()
    st.subheader("📤 一鍵 ISRC 匯入 (v15.12)")

    uploaded_csv = st.file_uploader(
        "上傳已回填 ISRC 的 DistroKid CSV",
        type=["csv"],
        key=f"isrc_upload_{cur_ch}",
        help="將從上方下載的 CSV 在 DistroKid 取得 ISRC 後回填，再上傳至此。",
    )

    if uploaded_csv is not None:
        # 暫存上傳檔案
        import tempfile, os as _os
        _tmp_dir = Path(tempfile.gettempdir()) / "ai_drama_isrc"
        _tmp_dir.mkdir(parents=True, exist_ok=True)
        _tmp_path = _tmp_dir / f"uploaded_isrc_{cur_ch}.csv"
        _tmp_path.write_bytes(uploaded_csv.getvalue())

        col_dry, col_go = st.columns(2)
        with col_dry:
            if st.button("🔍 預覽匯入 (Dry Run)", width="stretch", key=f"dryrun_{cur_ch}"):
                with st.spinner("預覽中..."):
                    res = st.session_state.backend.import_isrc_from_uploaded_csv(
                        str(_tmp_path), channel=cur_ch, dry_run=True
                    )
                if res["ok"]:
                    st.success(res["msg"])
                    if res["updated"] > 0:
                        st.caption(f"📊 預計寫入 {res['updated']} 筆 ISRC，略過 {res['skipped']} 筆")
                    if res["warnings"]:
                        st.warning("⚠️ 警告：" + "；".join(res["warnings"][:5]))
                else:
                    st.error(res["msg"])

        with col_go:
            confirm = st.checkbox("✅ 我已確認預覽結果無誤，允許寫入資料庫", key=f"confirm_isrc_{cur_ch}")
            if st.button(
                "✅ 正式匯入 ISRC",
                type="primary",
                width="stretch",
                disabled=not confirm,
                key=f"import_{cur_ch}",
            ):
                with st.spinner("寫入 ISRC 至資料庫中..."):
                    res = st.session_state.backend.import_isrc_from_uploaded_csv(
                        str(_tmp_path), channel=cur_ch, dry_run=False
                    )
                if res["ok"]:
                    st.success(res["msg"])
                    st.balloons()
                    st.rerun()
                else:
                    st.error(res["msg"])


with tab6:
    st.header("🛡️ 金庫維護與衍生歸零／歸檔清理")
    tgt = st.radio("重置目標", ["audio", "visual", "both"], horizontal=True)
    c1_rst = st.checkbox("我已確認備份重要資產", key="reset_c1")
    c2_rst = st.checkbox("明確授權將 derivation_count 歸零", key="reset_c2")
    if st.button("⚡ 執行金庫重置", disabled=not (c1_rst and c2_rst), type="primary"):
        ok, msg = st.session_state.backend.reset_derivation_counts(tgt)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)

    st.divider()
    st.subheader("🗑️ 歸檔音檔自動清理（超過30天壓縮備份並刪除）")
    c3_rst = st.checkbox("我已再次確認歸檔音檔已備份且可安全刪除", key="cleanup_c3")
    if st.button("🗃️ 一鍵清理歸檔音檔", disabled=not c3_rst, type="primary"):
        import subprocess
        try:
            result = subprocess.run([
                sys.executable,
                str(Path(__file__).parents[1] / "maintenance" / "cleanup_old_archived_beats.py")
            ], capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                st.success("清理完成！\n" + result.stdout)
            else:
                st.error(f"清理腳本執行失敗：{result.stderr}")
        except Exception as e:
            st.error(f"清理腳本執行異常：{e}")
