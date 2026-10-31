#!/bin/sh
# Live test (decisions.md §1206): the order-flow 30 s model (held-out IC 0.353 vs 0.252) for fair + pull; cap, join, units unchanged.
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
sed -i "s#model=/opt/mvtrx/agents/model30_live.json alpha_k=1.0 tape=/opt/mvtrx/live_tape_x1_units.jsonl#model=/opt/mvtrx/agents/model30_of.json alpha_k=1.0 tape=/opt/mvtrx/live_tape_x1_of.jsonl#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
