#!/bin/bash
# A94 (decisions.md 776): wall-clock scheduled LoL race recordings; each recording runs until its own end time, so a restart resumes it.
cd /home/coltontr419/futures-research
rec () {  # start end label
  now=$(date -u +%s); s=$(date -u -d "$1" +%s); e=$(date -u -d "$2" +%s)
  [ $now -ge $e ] && return
  while [ "$(date -u +%s)" -lt $s ]; do sleep 20; done
  hrs=$(python3 -c "print(($e-$(date -u +%s))/3600)")
  .venv/bin/python -m futuresres.esports.a94_lolrace "$3" "$hrs" >> logs/a94.log 2>&1
}
rec 2026-10-22T11:45:00Z 2026-10-22T15:45:00Z emea_1022
rec 2026-10-23T16:45:00Z 2026-10-24T03:45:00Z worlds_1023
