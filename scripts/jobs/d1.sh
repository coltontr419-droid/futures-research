#!/bin/bash
# D1 (decisions.md 869): DraftKings overlay recorder, until 2026-11-02 06:00Z (a full week incl. NFL Sunday; restarted 2026-10-26 after A-LIP ended, §1017). Resumable (appends).
cd /home/coltontr419/futures-research
hrs=$(python3 -c "import time,datetime as d;print(max(0,(d.datetime(2026,11,2,6,tzinfo=d.timezone.utc).timestamp()-time.time())/3600))")
exec .venv/bin/python -u -m futuresres.dfs.d1_overlay record "$hrs" >> logs/d1.log 2>&1
