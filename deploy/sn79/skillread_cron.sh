#!/bin/sh
# Early skill read every 2 h (decisions.md §1211 add. 29): validator-style alpha (skill_val.py) on the last 30 sim min of each tape.
# x2: "skipped" = its sleeve-only calm books (it does not trade x1s books); "calm" = its making books. x1: "skipped" = its sleeve books.
cd /opt/mvtrx; O=/opt/mvtrx/skill_reads.txt
echo "=== $(date -u +%m-%dT%H:%M) UTC" >> $O
echo "-- x2 (calm-book sleeve on skipped; making on calm)" >> $O; nice venv/bin/python skill_val.py live_tape_x2.jsonl 247 30 skip_x2.txt 2>&1 | grep -v Warn >> $O
echo "-- x1 (de-meaned reversed sleeve on skipped; volatile making on calm)" >> $O; nice venv/bin/python skill_val.py live_tape_x1_size6.jsonl 213 30 skip_x1.txt 2>&1 | grep -v Warn >> $O
P=https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query
for u in 247 213; do for g in debeta_skill debeta_skill_books_kept debeta_skill_rank; do printf "  uid %s live %s: " $u $g >> $O; curl -s -G "$P" --data-urlencode "query=miner_gauges{miner_gauge_name=\"$g\",agent_id=\"$u\"}" | python3 -c "import json,sys; print([round(float(r[\"value\"][1]),3) for r in json.load(sys.stdin)[\"data\"][\"result\"]])" >> $O 2>&1; done; done
