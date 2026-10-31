#!/bin/sh
# ReadyAI closed (decisions.md §1200): stop each miner as soon as its hotkey is no longer registered on SN33 (ends the OpenAI spend).
for i in $(seq 1 48); do
  left=$(/opt/tag101/venv/bin/python -c "
import sys; sys.path.insert(0, \"/opt/tag101\")
from minerwatch import miners
m = miners(33)
print(\" \".join(n for n in (\"r1\", \"r2\") if n in m))" 2>/dev/null) || { sleep 300; continue; }
  for r in r1 r2; do
    case " $left " in *" $r "*) ;; *) if systemctl is-active --quiet readyai-$r; then systemctl disable --now readyai-$r; echo "$(date -u +%H:%M) UTC stopped readyai-$r (deregistered)" >> /opt/readyai/closed.log; fi;; esac
  done
  [ -z "$left" ] && { echo "$(date -u +%H:%M) UTC both stopped; done" >> /opt/readyai/closed.log; exit 0; }
  sleep 300
done
