#!/bin/sh
# Live test step (decisions.md §1199): pull rule + join + tight inventory cap 5% and skew 6 (blocks adding to big positions, ~half the loss).
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
sed -i "s#skew=2.0 max_inv=0.25 edge=1 model=/opt/mvtrx/agents/model30_live.json alpha_k=1.0 tape=/opt/mvtrx/live_tape_x1_pull.jsonl join=1 pull=2.0#skew=6.0 max_inv=0.05 edge=1 model=/opt/mvtrx/agents/model30_live.json alpha_k=1.0 tape=/opt/mvtrx/live_tape_x1_invcap.jsonl join=1 pull=2.0#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
