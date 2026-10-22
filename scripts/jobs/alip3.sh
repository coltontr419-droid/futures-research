#!/bin/bash
# A-LIP3 (decisions.md 883): shadow quoting on all Kalshi Rotten Tomatoes rewards markets until 2026-10-26 01:00Z. Resumable (appends).
cd /home/coltontr419/futures-research
hrs=$(python3 -c "import time,datetime as d;print(max(0,(d.datetime(2026,10,26,1,tzinfo=d.timezone.utc).timestamp()-time.time())/3600))")
[ "$(python3 -c "print(float('$hrs')>0)")" = "True" ] || exit 0
ALIP_OUT=alip3 ALIP_INCLUDE=KXRT,KXSTREAMERAWARDS ALIP_N=1000 ALIP_CYCLE=120 exec .venv/bin/python -u -m futuresres.kalshi.alip2_shadow record "$hrs" >> logs/alip3.log 2>&1
