#!/bin/bash
# Restart the Mac-hosted ComfyUI instance (port 8188) with nohup logging.
#
# Usage (from the PC):  ssh MacM4 'bash /Volumes/AI_Workspace/AI_Drama_Factory/integrations/comfyui/restart_comfyui.sh'
# Canonical copy lives in repo scripts/mac/; the deployed copy sits next to the
# integration checkout on the Mac.  Verified 2026-09-13 (killed pid 55498,
# restarted with ComfyUI-GGUF loaded, /object_info returned the GGUF nodes).
set -u
COMFY_DIR=/Volumes/AI_Workspace/AI_Drama_Factory/integrations/comfyui
cd "$COMFY_DIR" || exit 1
OLDPID=$(pgrep -f "main.py --listen 0.0.0.0 --port 8188" || true)
if [ -n "$OLDPID" ]; then
  kill $OLDPID 2>/dev/null
  sleep 3
  echo "KILLED oldpid=$OLDPID"
fi
nohup ./.venv/bin/python main.py --listen 0.0.0.0 --port 8188 > /tmp/comfyui.log 2>&1 &
echo "RESTARTED newpid=$!"
