#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
將目前 Git 工作庫以 `git push --mirror` 推送到備份遠端（與 GitHub Actions 相同行為）。

環境變數 BACKUP_MIRROR_URL（與 Repo Secret 同名）：
  https://x-access-token:<PAT>@github.com/<OWNER>/<BACKUP_REPO>.git

可寫入專案根目錄 .env（已列於 .gitignore）；勿將含 token 的 URL 提交版本庫。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REMOTE_NAME = "rs-backup-mirror"


def _git_root() -> Path:
    p = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(p.stdout.strip())


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_git_root() / ".env", override=False)
    except ImportError:
        pass
    except OSError:
        pass


def _mask_url(url: str) -> str:
    if "x-access-token:" in url.lower():
        return re.sub(
            r"(x-access-token:)([^@]+)",
            r"\1***",
            url,
            flags=re.IGNORECASE,
        )
    if url.count("@") >= 2:
        return re.sub(r"//([^:]+):([^@]+)@", r"//\1:***@", url)
    return url


def main() -> int:
    parser = argparse.ArgumentParser(
        description="備份鏡像：git push --mirror 至 BACKUP_MIRROR_URL"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只檢查遠端與顯示將執行的指令，不實際推送",
    )
    args = parser.parse_args()

    _load_dotenv()
    url = (os.environ.get("BACKUP_MIRROR_URL") or "").strip()
    if not url:
        print(
            "錯誤：未設定 BACKUP_MIRROR_URL。請在專案根 .env 設定，或先 export。",
            file=sys.stderr,
        )
        print("說明：.github/BACKUP_REPO.md", file=sys.stderr)
        return 2

    root = _git_root()
    os.chdir(root)

    subprocess.run(
        ["git", "remote", "remove", REMOTE_NAME],
        capture_output=True,
        text=True,
    )
    subprocess.run(["git", "remote", "add", REMOTE_NAME, url], check=True)
    print(f"遠端 `{REMOTE_NAME}` → {_mask_url(url)}")

    cmd = ["git", "push", REMOTE_NAME, "--mirror"]
    if args.dry_run:
        print("[dry-run] " + " ".join(cmd))
        subprocess.run(["git", "remote", "remove", REMOTE_NAME], capture_output=True)
        return 0

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        subprocess.run(["git", "remote", "remove", REMOTE_NAME], capture_output=True)
        return 1

    subprocess.run(["git", "remote", "remove", REMOTE_NAME], capture_output=True)
    print("備份 mirror 推送完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
