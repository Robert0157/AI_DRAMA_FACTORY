#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DistroKid RPA Uploader (Safety-First Sandbox Edition)

【CTO 安全守則】
1) 預設只在本地 HTML 沙盒開發：file:///.../offline_upload.html
2) 強制 stealth + 慢速行為：slow_mo=500
3) 輸入採用人類打字延遲：type(..., delay=150)
4) 嚴禁自動按下最終送出按鈕：填表完成後 page.pause()
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from playwright.async_api import BrowserContext, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

try:
    # 新版 playwright-stealth（如 2.x）
    from playwright_stealth import stealth_async as _stealth_async
except ImportError:
    _stealth_async = None

try:
    # 1.0.1 版本提供 Stealth 類別
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.common.env_manager import config


AUTHOR_NAME = "R&S Echoes"
DEFAULT_OFFLINE_HTML = "assets/offline/offline_upload.html"
DEFAULT_METADATA_JSON = "assets/final_exports/metadata_distrokid.json"


@dataclass
class UploadPayload:
    title: str
    author: str
    genre: str
    audio_path: Path
    cover_path: Path | None


def _append_learning_and_exit(context: str, reason: str) -> None:
    learning_path = Path(config.workspace_root) / "project_learning.md"
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        "\n\n"
        f"## [{stamp}] Fatal: {context}\n"
        f"- 錯誤訊息: {reason}\n"
        "- 處置: 已中斷 DistroKid RPA，待人工確認。\n"
    )
    try:
        existing = learning_path.read_text(encoding="utf-8") if learning_path.exists() else ""
        learning_path.write_text(existing + entry, encoding="utf-8")
    except Exception:
        pass
    print(f"[FATAL] {context}: {reason}")
    sys.exit(1)


def _to_file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _read_cookie_pickle(cookie_path: Path) -> list[dict]:
    if not cookie_path.exists():
        return []
    try:
        raw = pickle.loads(cookie_path.read_bytes())
        if isinstance(raw, list):
            return [c for c in raw if isinstance(c, dict)]
    except Exception:
        return []
    return []


def _extract_industrial_title(name: str) -> str:
    match = re.search(r"([A-Za-z]{16}_\d{6}_\d{3})", name)
    if match:
        return match.group(1)
    return re.sub(r"[^A-Za-z0-9_-]", "", name)[:64]


def _load_metadata(metadata_path: Path) -> dict:
    if not metadata_path.exists():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_latest_audio() -> Path:
    approved_dir = Path(config.workspace_root) / "assets" / "audio" / "ceo_approved_beats"
    candidates = sorted(
        [p for p in approved_dir.glob("*.wav") if p.is_file()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        _append_learning_and_exit("DistroKid Input", "ceo_approved_beats/ 找不到 WAV 母帶")
    return candidates[0]


def _build_payload(metadata_path: Path) -> UploadPayload:
    metadata = _load_metadata(metadata_path)
    audio_path = _resolve_latest_audio()
    title = _extract_industrial_title(audio_path.stem)
    genre = str(metadata.get("spotify_subgenre", "lo-fi hip hop"))

    cover_candidate = Path(config.workspace_root) / "assets" / "image_anchors" / "cover.jpg"
    cover_path = cover_candidate if cover_candidate.exists() else None

    return UploadPayload(
        title=title,
        author=AUTHOR_NAME,
        genre=genre,
        audio_path=audio_path,
        cover_path=cover_path,
    )


async def _first_visible_locator(page: Page, selectors: Iterable[str]):
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0:
                return locator
        except Exception:
            continue
    return None


async def _human_fill(page: Page, selectors: list[str], text: str, label: str) -> None:
    locator = await _first_visible_locator(page, selectors)
    if locator is None:
        raise RuntimeError(f"找不到欄位: {label} | selectors={selectors}")

    # 先清空，再以人類節奏輸入（150ms/字）
    await locator.click(timeout=10_000)
    await locator.fill("")
    await locator.type(text, delay=150)
    print(f"[FORM] {label}: {text}")


async def _human_upload_file(page: Page, selectors: list[str], file_path: Path, label: str) -> None:
    locator = await _first_visible_locator(page, selectors)
    if locator is None:
        raise RuntimeError(f"找不到上傳欄位: {label}")
    await locator.set_input_files(str(file_path.resolve()))
    print(f"[UPLOAD] {label}: {file_path.name}")


async def _click_set_today_button(page: Page) -> None:
    # 點擊"設置為今天"按鈕來自動填入日期
    button_selectors = [
        "button#set-today-btn",
        "button[title='Set to today']",
        "button:has-text('📅')",
    ]
    for selector in button_selectors:
        try:
            locator = page.locator(selector).first
            if await locator.count() > 0:
                await locator.click()
                await page.wait_for_timeout(300)  # 等待 JS 觸發
                print("[FORM] ReleaseDate: ✅ 已點擊日期按鈕（設為今天）")
                return
        except Exception:
            continue
    raise RuntimeError("找不到日期設置按鈕 #set-today-btn")


async def _apply_stealth(page: Page, context: BrowserContext) -> None:
    # 相容兩種 playwright-stealth API：優先新式 stealth_async，否則退回 Stealth 類別
    if _stealth_async is not None:
        await _stealth_async(page)
        return
    if Stealth is not None:
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        return
    raise RuntimeError("playwright_stealth 不可用，請檢查相依套件安裝")


async def _prepare_context() -> tuple[BrowserContext, Page]:
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False, slow_mo=500)
    context = await browser.new_context()

    # 掛載 stealth，抹除 webdriver 特徵
    page = await context.new_page()
    await _apply_stealth(page, context)

    # 若有 cookie，僅在 live 模式可能用到；離線模式不依賴 cookie
    cookie_path = Path(config.distrokid_session_cookie_path)
    cookies = _read_cookie_pickle(cookie_path)
    if cookies:
        try:
            await context.add_cookies(cookies)
            print(f"[COOKIE] 載入 {len(cookies)} 筆 session cookies")
        except Exception as e:
            print(f"[COOKIE] 載入失敗（略過）: {e}")

    return context, page


async def run_sandbox(offline_html: Path, metadata_path: Path) -> None:
    if not offline_html.exists():
        _append_learning_and_exit("DistroKid Sandbox", f"離線 HTML 不存在: {offline_html}")

    payload = _build_payload(metadata_path)
    context, page = await _prepare_context()

    try:
        offline_url = _to_file_url(offline_html)
        await page.goto(offline_url, wait_until="domcontentloaded", timeout=30_000)
        print(f"[SANDBOX] 已載入: {offline_url}")

        # 表單欄位 selector 候選（可在本地 HTML 持續調整）
        await _human_fill(
            page,
            selectors=[
                "input[name='song_title']",
                "input[name='title']",
                "input#song-title",
                "input[placeholder*='Title']",
            ],
            text=payload.title,
            label="Title",
        )
        await _human_fill(
            page,
            selectors=[
                "input[name='artist_name']",
                "input[name='artist']",
                "input#artist-name",
                "input[placeholder*='Artist']",
            ],
            text=payload.author,
            label="Author",
        )
        await _human_fill(
            page,
            selectors=[
                "input[name='genre']",
                "input#genre",
                "input[placeholder*='Genre']",
            ],
            text=payload.genre,
            label="Genre",
        )
        await _click_set_today_button(page)

        await _human_upload_file(
            page,
            selectors=[
                "input[type='file'][name='audio_file']",
                "input[type='file'][accept*='audio']",
                "input#audio-upload",
            ],
            file_path=payload.audio_path,
            label="Audio",
        )

        if payload.cover_path is not None:
            await _human_upload_file(
                page,
                selectors=[
                    "input[type='file'][name='cover_file']",
                    "input[type='file'][accept*='image']",
                    "input#cover-upload",
                ],
                file_path=payload.cover_path,
                label="Cover",
            )

        # CEO 安全保險絲：禁止腳本自動點擊最終提交
        print("✅ 填表完成，等待 CEO 手動確認並送出...")
        print("[⏸️] 瀏覽器保持開啟。請在網頁上完成操作（包括點擊 Final Submit）。")
        print("[📝] 完成後，按 Enter 鍵關閉瀏覽器...")
        input()  # 等待使用者按 Enter
        print("[🔐] 關閉瀏覽器...")

    except PlaywrightTimeoutError as e:
        _append_learning_and_exit("DistroKid Sandbox", f"Playwright timeout: {e}")
    except Exception as e:
        _append_learning_and_exit("DistroKid Sandbox", str(e))
    finally:
        try:
            await context.close()
        except Exception:
            pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DistroKid RPA Uploader - Safety Sandbox")
    parser.add_argument(
        "--offline-html",
        type=str,
        default=DEFAULT_OFFLINE_HTML,
        help="本地 HTML 沙盒路徑（相對 workspace）",
    )
    parser.add_argument(
        "--metadata-json",
        type=str,
        default=DEFAULT_METADATA_JSON,
        help="Metadata JSON 路徑（相對 workspace）",
    )
    parser.add_argument(
        "--live-url",
        type=str,
        default="",
        help="保留參數：未啟用。初期禁止連線真實 DistroKid URL。",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    workspace_root = Path(config.workspace_root)

    offline_html = workspace_root / args.offline_html
    metadata_path = workspace_root / args.metadata_json

    # 依 CTO 安全守則：禁止線上盲測
    if args.live_url:
        _append_learning_and_exit(
            "DistroKid Safety Fuse",
            "檢測到 --live-url。依規範目前階段禁止連線 live URL。請使用本地 offline_upload.html。",
        )

    import asyncio

    asyncio.run(run_sandbox(offline_html=offline_html, metadata_path=metadata_path))


if __name__ == "__main__":
    main()
