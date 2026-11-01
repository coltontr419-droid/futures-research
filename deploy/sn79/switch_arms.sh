#!/bin/sh
# Start a new per-book A/B run (decisions.md §1207/§1209). usage: switch_arms.sh <new tape name> "<arms spec>" ["<base params to add>"]
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.arms.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/[A-Za-z0-9_]*\.jsonl#tape=/opt/mvtrx/$1.jsonl#; s# arms=[^ ]*##" $F
sed -i "s#\(tape=/opt/mvtrx/$1.jsonl .*\)\$#\1 arms=$2 $3#; s#  *\$##" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
