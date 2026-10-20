#!/bin/bash
# A96 (decisions.md 782): ProphetX vs Pinnacle snapshots every 10 min, indefinitely.
cd /home/coltontr419/futures-research
exec .venv/bin/python -m futuresres.sports.a96_prophetx record >> logs/a96.log 2>&1
