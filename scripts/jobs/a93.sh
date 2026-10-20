#!/bin/bash
# A93 (decisions.md 773): Kalshi x Polymarket US prop sweeps every 5 min until 2026-10-21 04:00Z (tonight's NBA games).
cd /home/coltontr419/futures-research
left=$(( $(date -u -d 2026-10-21T04:00:00Z +%s) - $(date -u +%s) )); [ $left -le 0 ] && exit 0
.venv/bin/python -m futuresres.kalshi.a93_props_xvenue $(( left / 300 + 1 )) >> logs/a93.log 2>&1
