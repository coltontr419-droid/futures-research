#!/bin/sh
# Add qlog=1 (decisions.md §1207: log our orders' size ahead in each queue; behaviour unchanged — replay byte-identical) to the live config,
# with a new tape. usage: switch_qlog.sh <current tape name> <new tape name>
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.q.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/$1.jsonl \(.*\)\$#tape=/opt/mvtrx/$2.jsonl \1 qlog=1#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
