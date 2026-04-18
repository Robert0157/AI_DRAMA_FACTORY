#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_suno_env.py — 從 .auth/audio_state.json 產生 suno-api/.env
用途：將 Playwright 存下的 Cookie 轉換為 gcui-art/suno-api 所需格式
"""
import json
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
AUTH_FILE    = PROJECT_ROOT / ".auth" / "audio_state.json"
ENV_OUT      = PROJECT_ROOT / "suno-api" / ".env"
ENV_EXAMPLE  = PROJECT_ROOT / "suno-api" / ".env.example"

def main():
    if not AUTH_FILE.exists():
        print(f"❌ 找不到 {AUTH_FILE}")
        sys.exit(1)

    data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))

    # 篩選 suno 相關 domain
    suno_domains = {"suno.com", ".suno.com", "auth.suno.com", "studio-api.prod.suno.com"}
    parts = [
        f'{c["name"]}={c["value"]}'
        for c in data.get("cookies", [])
        if c.get("domain") in suno_domains
    ]

    if not parts:
        print("❌ 未找到任何 suno.com Cookie，請確認 audio_state.json 來源正確")
        sys.exit(1)

    cookie_str = "; ".join(parts)
    # env_file 路徑不做 YAML 插值，Cookie 值直接寫入即可，無需 $$ 跳脫
    print(f"✅ 擷取 {len(parts)} 個 Cookie，總長 {len(cookie_str)} 字元")

    # 讀取 .env.example 作為模板，保留其他設定值
    example_lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines() if ENV_EXAMPLE.exists() else []
    out_lines = []
    cookie_written = False
    for line in example_lines:
        if line.startswith("SUNO_COOKIE="):
            out_lines.append(f"SUNO_COOKIE={cookie_str}")
            cookie_written = True
        else:
            out_lines.append(line)

    if not cookie_written:
        out_lines.insert(0, f"SUNO_COOKIE={cookie_str}")

    ENV_OUT.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    print(f"✅ 已寫入 {ENV_OUT}")
    print("   SUNO_COOKIE 前 60 字元:", cookie_str[:60], "...")

if __name__ == "__main__":
    main()
