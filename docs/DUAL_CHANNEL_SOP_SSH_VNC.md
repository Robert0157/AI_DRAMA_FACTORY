# Dual-Channel SOP (SSH + VNC)

This SOP defines how to operate 24/7 streaming with two channels:

- **SSH (Cursor SSH)** for code, scripts, logs, and automation.
- **VNC (TightVNC)** for GUI confirmation and web/backend visual checks.

Use this document as the execution checklist before each live run and as the first-response runbook during incidents.

## 1) Channel Responsibilities

### SSH side (primary control plane)

- Edit and run scripts in `scripts/streaming_steam/`.
- Validate files under `Streaming/config/`, `Streaming/queue/`, `Streaming/queue_staging/`.
- Start/restart ffmpeg pipeline and inspect logs.
- Perform deterministic checks (file count, bytes, process status, exit code).

### VNC side (visual verification plane)

- Confirm YouTube Studio stream state and health indicators.
- Confirm no blocking popups, permission prompts, or sleep dialogs.
- Confirm Finder/path visibility and mounted volume status.
- Confirm expected UI behavior when script says stream is active.

## 2) Pre-Flight: 3-Minute Checklist (Before Going Live)

Run in order. Do not skip.

### Minute 0-1: Environment and path sanity (SSH)

1. Confirm project root:
   - `cd /Volumes/AI_Workspace/AI_Drama_Factory`
2. Confirm required folders exist:
   - `Streaming/config`
   - `Streaming/queue`
   - `Streaming/secrets`
3. Confirm secret file exists (without printing key):
   - `test -f Streaming/secrets/rtmp.env && echo OK || echo MISSING`
4. Confirm ffmpeg exists:
   - `/opt/homebrew/bin/ffmpeg -version`

### Minute 1-2: Playlist and media readiness (SSH)

1. Validate manifest/concat generation path:
   - Run the repo-standard concat build flow (see `scripts/streaming_steam/README.md`).
2. Confirm concat file exists and non-empty:
   - `test -s Streaming/config/concat_playlist.txt && echo OK || echo EMPTY`
3. Quick media inventory check:
   - `python3 - <<'PY'`
   - `import os`
   - `root='Streaming/queue'`
   - `n=sum(len(f) for _,_,f in os.walk(root))`
   - `print('QUEUE_FILES=', n)`
   - `PY`

### Minute 2-3: Stream startup and visual confirmation (SSH + VNC)

1. Start stream from SSH using project script.
2. On VNC, open YouTube Studio live control room:
   - Confirm ingest is detected.
   - Confirm stream health is green/yellow (not red).
3. Wait for first stable video/audio preview.
4. Record start time and script/log reference for later debugging.

## 3) Live Monitoring Rhythm (After Start)

### Every 10-15 minutes (SSH)

- Confirm ffmpeg process still alive.
- Confirm log is still advancing (new timestamps).
- Confirm no repeated reconnect loop messages.

### Every 10-15 minutes (VNC)

- Confirm Studio stream still receiving data.
- Confirm no UI warnings (copyright/bitrate/network/auth prompts).
- Confirm preview remains continuous (no black frame freeze).

## 4) Incident Response: Fast Triage Flow

Follow this sequence to reduce recovery time.

### A. Stream is offline in Studio

1. **SSH**: check ffmpeg process.
2. **SSH**: check latest log lines for auth/network/playlist errors.
3. **SSH**: verify `rtmp.env` exists and has expected variable names.
4. **VNC**: refresh Studio page and confirm event is still active.
5. Restart stream script once after root cause is identified.

### B. ffmpeg exits repeatedly (restart loop)

1. Check concat file integrity and referenced media existence.
2. Confirm volume is mounted: `/Volumes/AI_Workspace/...`.
3. Confirm no moved/deleted media in active queue during playback.
4. If recent rotation happened, rebuild concat and restart once.

### C. Video present but no audio / A/V abnormal

1. Re-run with a known-good test clip in queue.
2. Check ffmpeg parameters in run script and recent edits.
3. Confirm source media codec consistency (problematic file isolation).
4. Validate in Studio preview and local quick playback via VNC.

### D. Sync lag between Windows and Mac content

1. Use wired host path and run sync script/task from Windows.
2. Compare file counts/bytes local vs Mac `Streaming`.
3. Upload only missing files if full sync is too slow.

## 5) Recovery Modes

### Soft recovery (preferred)

- Rebuild concat.
- Restart stream script.
- Verify in Studio within 1-2 minutes.

### Hard recovery (when soft fails)

- Stop stream process cleanly.
- Re-validate secrets, paths, mount state.
- Run a known-good minimal media set.
- Start stream and confirm green ingest before restoring full queue.

## 6) Operational Guardrails

- Do not commit secrets (`Streaming/secrets/rtmp.env`).
- Do not run destructive git operations during active incident handling.
- Keep changes minimal while live; defer refactors until stable window.
- Any hotfix during live run must be documented in `docs/AGENT_HANDOFF.md`.

## 7) Handoff Note Template (Post-Incident or Post-Run)

Copy this to your running notes or handoff doc:

```text
Run window:
- Start time:
- End time:

Status:
- Stream health:
- Interruptions:

Actions taken:
- (1)
- (2)

Evidence:
- SSH command outputs:
- Log file(s):
- VNC/Studio observations:

Next recommended step:
- ...
```

