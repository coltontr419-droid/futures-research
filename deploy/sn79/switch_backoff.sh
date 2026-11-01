#!/bin/sh
# Live test (decisions.md §1207): stronger flow back-off — flow_win=10 flow_cool=3 on the live flow_pull=0.3 (backoff_scan.py out of sample:
# kept fills ≈ +0.05 ticks with 67% kept, vs −0.16 / 76% for the 5 s window without cooldown). Everything else unchanged.
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.bo.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/live_tape_x1_flowpull.jsonl \(.*\) flow_pull=0.3#tape=/opt/mvtrx/live_tape_x1_backoff.jsonl \1 flow_pull=0.3 flow_win=10 flow_cool=3#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
