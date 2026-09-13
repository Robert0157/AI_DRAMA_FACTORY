#!/bin/sh
# Run the TCC contract probe under launchd and print results (Mac side; keeps Windows quoting out of the loop).
echo '---probe file bytes---'
od -c '/Users/robert/Library/Application Support/AI_Drama_Factory/tcc_probe.sh' 2>/dev/null | head -2
ls -la /tmp/tcc_probe.out* 2>/dev/null
echo '---job state---'
launchctl print gui/501/com.aidramafactory.tccprobe 2>/dev/null | grep -E 'state =|last exit code|runs =' | head -4
echo '---submit probe---'
tr -d '\r' < '/Volumes/AI_Workspace/AI_Drama_Factory/logs/tcc_probe.sh' > /tmp/tcc_probe.sh
chmod +x /tmp/tcc_probe.sh
launchctl remove tccprobe2 2>/dev/null
launchctl submit -l tccprobe2 -- /bin/sh /tmp/tcc_probe.sh
sleep 30
echo '===RESULT==='
cat /tmp/tcc_probe.out 2>/dev/null
launchctl remove tccprobe2 2>/dev/null
echo '---comfy owner---'
launchctl list | grep -i comfy
echo SUBMIT_PROBE_DONE
