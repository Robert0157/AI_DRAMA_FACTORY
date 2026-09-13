#!/bin/sh
# TCC contract probe: which tools can open files on the external volume from a launchd context?
LOG=/tmp/tcc_probe.out
: > $LOG
F="/Volumes/AI_Workspace/AI_Drama_Factory/assets/audio/ceo_approved_beats/lofi/CinematicAnthem_FallingStars.mp3"
echo "whoami=$(whoami) date=$(date)" >> $LOG
echo "--- ffprobe ---" >> $LOG
( /opt/homebrew/bin/ffprobe -v error -show_entries format=duration -of default=nw=1 "$F" >> $LOG 2>&1 ) &
PID=$!; SECS=0
while kill -0 $PID 2>/dev/null && [ $SECS -lt 20 ]; do sleep 1; SECS=$((SECS+1)); done
if kill -0 $PID 2>/dev/null; then kill -9 $PID; echo "FFPROBE=HUNG" >> $LOG; else echo "FFPROBE=OK" >> $LOG; fi
echo "--- ffmpeg ---" >> $LOG
( /opt/homebrew/bin/ffmpeg -hide_banner -v error -t 1 -i "$F" -f null - >> $LOG 2>&1 ) &
PID=$!; SECS=0
while kill -0 $PID 2>/dev/null && [ $SECS -lt 20 ]; do sleep 1; SECS=$((SECS+1)); done
if kill -0 $PID 2>/dev/null; then kill -9 $PID; echo "FFMPEG=HUNG" >> $LOG; else echo "FFMPEG=OK" >> $LOG; fi
echo "--- python3 ---" >> $LOG
/usr/bin/python3 -c "open('$F','rb').read(1024); print('PY_OPEN=OK')" >> $LOG 2>&1
echo DONE >> $LOG
