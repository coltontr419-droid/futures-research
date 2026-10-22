#!/bin/bash
# G1 (decisions.md 888): Gemini Predictions NFL reward shadow until 2026-10-27 06:00Z. Resumable (appends).
cd /home/coltontr419/futures-research
hrs=$(python3 -c "import time,datetime as d;print(max(0,(d.datetime(2026,10,27,6,tzinfo=d.timezone.utc).timestamp()-time.time())/3600))")
[ "$(python3 -c "print(float('$hrs')>0)")" = "True" ] || exit 0
exec .venv/bin/python -u -m futuresres.sports.g1_gemini record "$hrs" >> logs/g1.log 2>&1
