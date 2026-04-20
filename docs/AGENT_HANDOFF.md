# AGENT HANDOFF (Windows -> Mac Mini)

## Read Order (Do This First)

Use this exact reading sequence in every brand-new agent session:

1. Must read first:
   - `docs/AGENT_HANDOFF.md`
   - `scripts/streaming_steam/README.md`
2. Read on demand (only when the current task needs it):
   - `scripts/streaming_steam/*` (open only the script(s) being changed or validated)
   - `Streaming/config/*` (when validating manifest/concat behavior)
3. Reference only (do not read fully unless needed for cross-module context):
   - `架構說明書_v15.10.md`
   - other spec/workflow documents

Execution rule for fresh agents:

- First, summarize current status in 3-6 bullets based on the two must-read files.
- Then propose the smallest safe next step and execute it with verifiable output.
- Any additional file reads must include a one-line reason.

This document is the single source of truth for starting a fresh agent session on Mac Mini and continuing work from the Windows environment without losing context.

## Scope and Goal

- Focus only on the 24/7 streaming minimum viable pipeline.
- Do not expand scope to unrelated systems unless explicitly requested.
- Keep changes incremental, verifiable, and reversible.

## Environment Snapshot

- Windows workspace root: `F:\AI_DRAMA_FACTORY`
- Mac workspace root: `/Volumes/AI_Workspace/AI_Drama_Factory`
- Preferred wired SSH host: `robert@192.168.1.102`
- OS note:
  - Windows side runs PowerShell commands and transfer scripts.
  - Mac side runs shell scripts (`.sh`) and ffmpeg workflow.

## What Has Been Completed

1. Streaming data sync status:
   - Full `Streaming` synchronization has been completed from Windows to Mac.
   - Verification result: all local Windows `Streaming` files exist on Mac with matching file sizes.
   - Last verified local totals:
     - `LOCAL_FILES=27`
     - `LOCAL_BYTES=19169001600`
   - Last verified remote totals:
     - `REMOTE_FILES=29`
     - `REMOTE_BYTES=19169014015`
   - Remote extra files (expected and acceptable):
     - `.DS_Store`
     - `secrets/rtmp.env.template`

2. Streaming script hardening:
   - `scripts/streaming_steam/run_youtube_rtmp.sh` has been aligned to work under non-interactive sessions by handling PATH and preferring absolute ffmpeg path when needed.
   - Known working ffmpeg path on Mac: `/opt/homebrew/bin/ffmpeg`

3. Queue staging sync tooling:
   - Added `scripts/streaming_steam/sync_queue_staging_to_mac.ps1`
   - Added scheduler guide `scripts/streaming_steam/WINDOWS_TASK_SCHEDULER_queue_staging.md`
   - README table updated to include the above scripts.

## Current Operational Notes

- `launchd` RTMP auto-start had previously failed because `Streaming/secrets/rtmp.env` was missing.
- Template exists, but real secrets file still needs to be provided before unattended RTMP push can run.
- Use wired host (`192.168.1.102`) for larger transfers and stability.

## Priority TODOs (Next Agent Should Continue Here)

1. Secrets readiness
   - Ensure `Streaming/secrets/rtmp.env` exists on Mac with valid values.
   - Do not commit secrets into git.

2. End-to-end smoke test
   - Validate manifest + concat generation + ffmpeg startup on Mac.
   - Run a short private/unlisted YouTube test stream first.

3. Rotation + playback continuity
   - Validate `rotate_live_slot.sh` and manifest update flow with staged content.
   - Confirm behavior when queue/staging content is low or missing.

4. Scheduling reliability
   - If Windows scheduler is enabled, verify task history and exit codes over multiple intervals.
   - Ensure concurrent runs are prevented (no overlapping sync jobs).

## Constraints and Guardrails

- Do not reset or discard unrelated local changes.
- Do not force push or run destructive git operations.
- Keep `.sh` files in LF line endings.
- Keep streaming workflow as the current top priority.

## Quick Verification Commands

Use these on Mac to quickly validate environment and data presence:

```bash
cd /Volumes/AI_Workspace/AI_Drama_Factory
python3 - <<'PY'
import os
r='Streaming'
files=0
bytes_=0
for dp,_,fns in os.walk(r):
    for fn in fns:
        p=os.path.join(dp,fn)
        try:
            st=os.stat(p)
        except OSError:
            continue
        files += 1
        bytes_ += st.st_size
print('FILES=', files)
print('BYTES=', bytes_)
PY
```

## Recommended New-Agent Kickoff Prompt

Copy/paste this into a brand-new agent session:

```text
Please read these files first and do not code before summarizing:
1) docs/AGENT_HANDOFF.md
2) scripts/streaming_steam/README.md

Then:
- Summarize current status in 3-6 bullets.
- Propose the smallest safe next step for the streaming pipeline.
- Execute that step with verifiable command output.

Constraints:
- Stay within streaming_steam scope.
- Do not touch unrelated systems.
- Do not revert unrelated working tree changes.
```

## Handoff Update Rule

Whenever a milestone is completed (sync verification, secrets configured, test stream pass, scheduler stabilized), update this file immediately so the next fresh agent can continue with minimal context loss.
