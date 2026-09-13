"""Capture reproducible offline QA evidence without approving production release."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

if str(Path(__file__).resolve().parents[2]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.common.env_manager import EnvConfig


TESTS = (
    "tests/test_script_forge.py",
    "tests/test_mac_wan_worker.py",
    "tests/test_dispatch_steps_policy.py",
    "tests/test_dispatch_to_mac_path.py",
    "tests/test_music_timeline.py",
    "Auto_Drama/tests/test_lmd_video_guards.py",
)
MIN_EXPECTED_TESTS = 89
SOURCES = (
    "scripts/story_room/script_forge.py",
    "scripts/pipeline/mac_wan_worker.py",
    "scripts/pipeline/dispatch_to_mac.py",
    "scripts/pipeline/music_timeline.py",
    "Auto_Drama/auto_drama/lmd_video_chain.py",
    "scripts/maintenance/verify_dual_line_release.py",
    *TESTS,
)
RELEASE_BLOCKERS = (
    "Mac production deployment and restart acceptance not established by this test run",
    "Persistent authenticated approvals and publishing enforcement remain incomplete",
    "Music-aware editing, visual reference workflows and variation QC remain incomplete",
    "B-line CP-D/CP1/CP2 end-to-end acceptance and production freeze authorization outstanding",
    "Human visual quality review, reference-film analysis and capacity acceptance outstanding",
)


def fingerprints(root: Path) -> dict[str, str]:
    """Bind evidence to the exact sources and tests that were executed."""
    return {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest() for relative in SOURCES}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="new evidence directory inside WORKSPACE_ROOT")
    args = parser.parse_args()
    root = EnvConfig().workspace_root.resolve()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = (root / args.output).resolve() if args.output else root / "CEO" / "04_架構檢視" / "驗證證據" / run_id
    if not output.is_relative_to(root):
        raise ValueError("evidence must remain inside WORKSPACE_ROOT")
    output.mkdir(parents=True, exist_ok=False)
    before = fingerprints(root)
    tools = {}
    for name in ("ffmpeg", "ffprobe"):
        executable = shutil.which(name)
        if executable:
            version = subprocess.run([executable, "-version"], capture_output=True, text=True, timeout=15)
            tools[name] = {"available": version.returncode == 0,
                           "version": version.stdout.splitlines()[0] if version.stdout else "unknown"}
        else:
            tools[name] = {"available": False}
    junit = output / "pytest.xml"
    with tempfile.TemporaryDirectory(prefix=".dual-line-qa-", dir=root) as temporary:
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                   "--basetemp", temporary, "--junitxml", str(junit), *TESTS]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=300,
                                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    (output / "pytest.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (output / "pytest.stderr.txt").write_text(result.stderr, encoding="utf-8")
    counts = {name: 0 for name in ("tests", "failures", "errors", "skipped")}
    if junit.is_file():
        for suite in ET.parse(junit).getroot().iter("testsuite"):
            for name in counts:
                counts[name] += int(suite.get(name, "0"))
    after = fingerprints(root)
    passed = (result.returncode == 0 and counts["tests"] >= MIN_EXPECTED_TESTS and not counts["skipped"]
              and not counts["failures"] and not counts["errors"] and before == after
              and all(tool["available"] for tool in tools.values()))
    evidence = {
        "schema": "dual_line.qa.v1", "run_id": run_id,
        "scope": "offline_regression_and_synthetic_ffmpeg_only",
        "engineering_status": "PASS" if passed else "FAIL",
        "production_release": "BLOCKED", "release_blockers": RELEASE_BLOCKERS,
        "python": sys.version, "interpreter": sys.executable, "platform": platform.platform(),
        "dependencies": {name: importlib.metadata.version(name) for name in ("pytest", "requests", "python-dotenv")},
        "tools": tools, "test_command": command, "test_exit_code": result.returncode,
        "counts": counts, "minimum_expected_tests": MIN_EXPECTED_TESTS,
        "source_sha256": before, "sources_unchanged_during_tests": before == after,
    }
    (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    print(f"ENGINEERING_QA={evidence['engineering_status']} PRODUCTION_RELEASE=BLOCKED")
    print(f"EVIDENCE={output}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())