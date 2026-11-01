#!/bin/sh
# Live test (decisions.md §1207): flow_pull=0.3 on top of the fast path — drop the exposed side while near-touch new-order imbalance (5 s) leans
# against it (pull_scan.py: on 3 live tapes the fills it blocks average −1.8 to −2.7 ticks, the rest +0.24 to +0.48). Everything else unchanged.
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.fp.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/live_tape_x1_fast.jsonl join=1 pull=1.0 max_units=20 lean=1 raw=1 lazy_load=1#tape=/opt/mvtrx/live_tape_x1_flowpull.jsonl join=1 pull=1.0 max_units=20 lean=1 raw=1 lazy_load=1 flow_pull=0.3#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
