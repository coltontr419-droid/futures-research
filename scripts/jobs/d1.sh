#!/bin/bash
# D1 (decisions.md 869): DraftKings overlay recorder, until 2026-10-27 03:00Z (covers a weekend). Resumable (appends).
cd /home/coltontr419/futures-research
hrs=$(python3 -c "import time,datetime as d;print(max(0,(d.datetime(2026,10,27,3,tzinfo=d.timezone.utc).timestamp()-time.time())/3600))")
exec .venv/bin/python -u -m futuresres.dfs.d1_overlay record "$hrs" >> logs/d1.log 2>&1
