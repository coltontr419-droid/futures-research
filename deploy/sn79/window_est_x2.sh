#!/bin/sh
# Size test window estimate for UID ${UID2:-0} (decisions.md §1211 addendum 3): size 0.06 / max_inv 0.3 / max_units 60 from the restart (sim min 96.6),
# through the exact making code, plus the live public gauges. Appends to /opt/mvtrx/window_readouts_x2.txt.
O=/opt/mvtrx/window_readouts_x2.txt
echo "=== $(date -u +%H:%M) UTC (size 0.06, UID ${UID2:-0})" >> $O
cd /opt/mvtrx/repo && nice -n 10 /opt/mvtrx/venv/bin/python /opt/mvtrx/making_exact.py /opt/mvtrx/live_tape_x2.jsonl ${UID2:-0} 1 2>&1 | grep -E "^ours|two-sided|^field:" >> $O
P=https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query
for g in debeta_making debeta_making_rank debeta_skill debeta_skill_rank combined_score score; do
  printf "  live %s: " $g >> $O
  curl -s -G "$P" --data-urlencode "query=miner_gauges{miner_gauge_name=\"$g\",agent_id=\"${UID2:-0}\"}" | /opt/mvtrx/venv/bin/python -c "import json,sys; print([round(float(r[\"value\"][1]),4) for r in json.load(sys.stdin)[\"data\"][\"result\"]])" >> $O 2>&1
done
