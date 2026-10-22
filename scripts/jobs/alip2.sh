#!/bin/bash
# A-LIP2 (decisions.md 878): shadow competitive quoting recorder until 2026-10-26 01:00Z (3 days). Resumable (appends).
cd /home/coltontr419/futures-research
hrs=$(python3 -c "import time,datetime as d;print(max(0,(d.datetime(2026,10,26,1,tzinfo=d.timezone.utc).timestamp()-time.time())/3600))")
[ "$(python3 -c "print(float('$hrs')>0)")" = "True" ] || exit 0
exec .venv/bin/python -u -m futuresres.kalshi.alip2_shadow record "$hrs" >> logs/alip2.log 2>&1
