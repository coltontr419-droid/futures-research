#!/bin/sh
# Live test (decisions.md §1207): sticky=1 on the live flow_pull setup — keep a resting order when the target moves up to 1 tick more aggressive,
# instead of re-placing it at the back of the queue (62% of our fills come just before the level is swept, vs 41% for the field).
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.st.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/live_tape_x1_flowpull.jsonl \(.*\) flow_pull=0.3\$#tape=/opt/mvtrx/live_tape_x1_sticky.jsonl \1 flow_pull=0.3 sticky=1#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
