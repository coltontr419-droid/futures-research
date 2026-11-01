#!/bin/sh
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
sed -i "s# edge=2 # edge=1 #; s#tape=/opt/mvtrx/live_tape_x1_edge2.jsonl \(.*\)\$#tape=/opt/mvtrx/live_tape_x1_cancelfirst.jsonl \1 cancel_first=1#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
