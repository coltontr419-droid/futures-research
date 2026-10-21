#!/bin/bash
# A98 (decisions.md 794): Pinnacle vs Kalshi game lines every ~20 s, indefinitely.
cd /home/coltontr419/futures-research
exec .venv/bin/python -u -m futuresres.sports.a98_steam record >> logs/a98.log 2>&1
