#!/bin/sh
# Live test (decisions.md §1207): cancel_first=1 on whatever setup is live — cancel the side the prediction says is exposed first (the validator
# adds 5-25 ms to every instruction after a book's first). Pass the current tape name and a new one: switch_cancelfirst.sh <old> <new>
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.bo.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/$1.jsonl \(.*\)\$#tape=/opt/mvtrx/$2.jsonl \1 cancel_first=1#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
