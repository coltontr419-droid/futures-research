#!/bin/sh
# Live test step (decisions.md §1199): rest 2 ticks behind the best price (snipers take the touch), keep pull + inventory cap.
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
sed -i "s# tape=/opt/mvtrx/live_tape_x1_invcap.jsonl join=1 pull=2.0# tape=/opt/mvtrx/live_tape_x1_back.jsonl join=1 pull=2.0 back=2#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
