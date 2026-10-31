#!/bin/sh
# Live test (decisions.md §1207): speed only. raw=1 lean=1 lazy_load=1: QuoteAgent reads the wire dicts directly and skips the base agent's
# history / CSV log / debug text. Replay of 3 live states (15 runs): 0.237 → 0.080 s per state; orders and tape byte-identical (replay.py).
# cancel_first stays off (its own later test).
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.raw.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/live_tape_x1_pull1.jsonl join=1 pull=1.0 max_units=20#tape=/opt/mvtrx/live_tape_x1_fast.jsonl join=1 pull=1.0 max_units=20 lean=1 raw=1 lazy_load=1#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
