#!/bin/sh
# Scheduled live test step 2 (decisions.md §1199): no-predictor baseline -> live-fitted 30 s predictor x1, join mode kept.
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
sed -i "s#model=/opt/mvtrx/agents/model60.json alpha_k=0.0 tape=/opt/mvtrx/live_tape_x1_nopred.jsonl join=1#model=/opt/mvtrx/agents/model30_live.json alpha_k=1.0 tape=/opt/mvtrx/live_tape_x1_livemodel.jsonl join=1#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "model=.*" $F)" >> /opt/mvtrx/switch_live_model.log
