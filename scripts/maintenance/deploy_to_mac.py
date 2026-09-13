#!/usr/bin/env python3
"""Deploy a verified qa_releases stage to Mac production paths (files only).

Runbook step (双線改善手冊 §7): snapshot -> deploy -> verify hashes.
--rollback restores a previous deployment from its rollback directory.
This script never starts/stops services, never touches databases or media;
service restart and in-production verification follow the runbook by hand.

Usage:
  python scripts/maintenance/deploy_to_mac.py                    # latest stage
  python scripts/maintenance/deploy_to_mac.py --stage <dir> --dry-run
  python scripts/maintenance/deploy_to_mac.py --rollback <deploy_log.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from scripts.pipeline.dispatch_to_mac import SMB_ROOT  # noqa: E402

QA_REL = Path("Auto_Drama/output/qa_releases")


def sha256_of(path: Path) -> str:
    """Hash a file with SMB retry (the Y: share can hiccup with WinError 58)."""
    for attempt in range(4):
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def _exists(path: Path) -> bool:
    """is_file with SMB retry."""
    for attempt in range(4):
        try:
            return path.is_file()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(0.5 * (attempt + 1))
    return False


def _copy(src: Path, dst: Path) -> None:
    """copy2 with SMB retry."""
    for attempt in range(4):
        try:
            shutil.copy2(src, dst)
            return
        except OSError:
            if attempt == 3:
                raise
            time.sleep(0.5 * (attempt + 1))


def _is_link_or_special(path: Path) -> bool:
    """Symlink/special target on the share (Windows stat raises WinError 58 on these)."""
    try:
        return path.is_symlink()
    except OSError:
        return True


def latest_stage(qa_root: Path) -> Path:
    stages = sorted(p for p in qa_root.glob("2*") if (p / "deployment_manifest.json").is_file())
    if not stages:
        raise SystemExit(f"[FATAL] no stage with deployment_manifest.json under {qa_root}")
    return stages[-1]


def load_manifest(stage: Path) -> dict[str, str]:
    manifest = json.loads((stage / "deployment_manifest.json").read_text(encoding="utf-8"))
    return {rel.replace("\\", "/"): digest for rel, digest in manifest.items()}


def deployable(rel: str) -> bool:
    """Production payload: code/tests only; never stage-internal evidence."""
    return rel.endswith(".py") and not rel.startswith("CEO/")


def deploy(stage: Path, dry_run: bool) -> int:
    manifest = {rel: d for rel, d in load_manifest(stage).items() if deployable(rel)}
    if not manifest:
        raise SystemExit("[FATAL] manifest has no deployable files")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rollback_dir = SMB_ROOT / QA_REL / f"rollback_{stamp}"
    log: dict = {"stage": str(stage), "rollback_dir": str(rollback_dir), "files": {}}
    missing = [rel for rel in manifest if not (stage / rel).is_file()]
    if missing:
        raise SystemExit(f"[FATAL] stage missing files: {missing[:5]}")

    for rel, digest in sorted(manifest.items()):
        src = stage / rel
        dst = SMB_ROOT / rel
        actual = sha256_of(src)
        if actual != digest:
            raise SystemExit(f"[FATAL] stage file {rel} changed since verification")
        if _is_link_or_special(dst):
            print(f"[skip] {rel}: target is a symlink/special file on the share "
                  "(update its reference target separately)")
            continue
        entry = {"src_sha256": digest, "existed": _exists(dst), "pre_sha256": None}
        if entry["existed"]:
            entry["pre_sha256"] = sha256_of(dst)
        if dry_run:
            print(f"[dry-run] {rel}  existing={entry['existed']}")
        else:
            if entry["existed"]:
                backup = rollback_dir / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                _copy(dst, backup)
            dst.parent.mkdir(parents=True, exist_ok=True)
            _copy(src, dst)
            if sha256_of(dst) != digest:
                raise SystemExit(f"[FATAL] deployed file hash mismatch: {rel}")
        log["files"][rel] = entry

    if dry_run:
        print(f"[dry-run] would deploy {len(manifest)} files; stage={stage}")
        return 0
    rollback_dir.mkdir(parents=True, exist_ok=True)
    log_path = rollback_dir / "deploy_log.json"
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DEPLOY_OK files={len(manifest)} rollback_dir={rollback_dir}")
    print("NEXT: restart services on Mac, run verify_dual_line_release.py in production, "
          "then a low-steps engineering smoke job (runbook §7).")
    return 0


def rollback(log_path: Path) -> int:
    log = json.loads(log_path.read_text(encoding="utf-8"))
    rollback_dir = Path(log["rollback_dir"])
    restored = 0
    for rel, entry in sorted(log["files"].items()):
        if not entry.get("existed"):
            print(f"[rollback] {rel}: did not exist before; remove by hand if needed")
            continue
        backup = rollback_dir / rel
        dst = SMB_ROOT / rel
        if not _exists(backup):
            raise SystemExit(f"[FATAL] rollback copy missing: {backup}")
        _copy(backup, dst)
        if sha256_of(dst) != entry["pre_sha256"]:
            raise SystemExit(f"[FATAL] rollback hash mismatch: {rel}")
        restored += 1
    print(f"ROLLBACK_OK restored={restored} from={rollback_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", help="qa_releases stage dir (default: latest)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", help="deploy_log.json to roll back")
    args = parser.parse_args()

    if args.rollback:
        return rollback(Path(args.rollback))
    stage = Path(args.stage) if args.stage else latest_stage(SMB_ROOT / QA_REL)
    print(f"stage: {stage}")
    return deploy(stage, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
