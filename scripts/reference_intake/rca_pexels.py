#!/usr/bin/env python3
"""RCA helper: verify stock-API keys (Pexels / Pixabay) without printing secrets.

Prints only a fingerprint (length + sha256 prefix) plus the live HTTP result,
so logs stay safe to share. Usage:
  python3 rca_pexels.py                        # Mac default env file
  python3 rca_pexels.py --env-file <path>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ENV = Path.home() / "Library/Application Support/AI_Drama_Factory/reference_intake.env"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def fingerprint(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:8]
    return f"len={len(value)} sha256[:8]={digest}"


def http_get(url: str, headers: dict[str, str]) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read(400).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read(400).decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body
    except Exception as exc:  # noqa: BLE001 - diagnostic tool reports everything
        return -1, f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    args = parser.parse_args()

    env_path = Path(args.env_file)
    env = load_env(env_path)
    report: dict[str, object] = {"env_file": str(env_path), "exists": env_path.is_file(), "checks": {}}

    checks: dict[str, object] = {}
    pexels_key = env.get("PEXELS_API_KEY", "")
    pexels_url = "https://api.pexels.com/v1/search?query=nature&per_page=1"
    if not pexels_key:
        checks["pexels"] = {"key": "MISSING", "verdict": "key-absent-in-env-file"}
    else:
        # 3-case probe matrix: distinguishes revoked key vs Cloudflare bot-blocking.
        matrix = {
            "key+pythonUA": http_get(pexels_url, {"Authorization": pexels_key}),
            "key+browserUA": http_get(pexels_url, {"Authorization": pexels_key, "User-Agent": BROWSER_UA}),
            "nokey+pythonUA": http_get(pexels_url, {}),
        }
        codes = [code for code, _ in matrix.values()]
        if 200 in codes:
            verdict = "OK"
        elif codes[1] in (401, 403) and codes[0] == codes[1]:
            verdict = "KEY-OR-ACCOUNT-BLOCKED (UA-independent)"
        elif codes[0] in (401, 403) and codes[1] == 200:
            verdict = "CLOUDFLARE-UA-BLOCK (browser UA passes)"
        else:
            verdict = "MIXED-CHECK-MATRIX"
        checks["pexels"] = {
            "key": fingerprint(pexels_key),
            "matrix": {k: {"http": c, "body_head": b[:160]} for k, (c, b) in matrix.items()},
            "verdict": verdict,
        }

    pixabay_key = env.get("PIXABAY_API_KEY", "")
    if not pixabay_key:
        checks["pixabay"] = {"key": "MISSING", "http": None, "verdict": "key-absent-in-env-file"}
    else:
        code, body = http_get(
            f"https://pixabay.com/api/?key={pixabay_key}&q=nature&per_page=3",
            {},
        )
        verdict = "OK" if code == 200 else ("INVALID" if code == 400 else f"HTTP-{code}")
        checks["pixabay"] = {"key": fingerprint(pixabay_key), "http": code, "body_head": body[:200], "verdict": verdict}

    report["checks"] = checks
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
