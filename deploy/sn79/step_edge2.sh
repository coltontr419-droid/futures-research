#!/bin/sh
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
sed -i "s# edge=1 # edge=2 #; s#tape=/opt/mvtrx/live_tape_x1_fast2.jsonl#tape=/opt/mvtrx/live_tape_x1_edge2.jsonl#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
