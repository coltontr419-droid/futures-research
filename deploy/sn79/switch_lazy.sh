#!/bin/sh
# Live test (decisions.md §1207): lazy state parsing (≈ half our answer time) + exposed-side cancel first; params otherwise unchanged.
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.new.py /opt/mvtrx/agents/QuoteAgent.py
sed -i "s#tape=/opt/mvtrx/live_tape_x1_pull1.jsonl join=1 pull=1.0 max_units=20#tape=/opt/mvtrx/live_tape_x1_lazy.jsonl join=1 pull=1.0 max_units=20 lazy_load=1#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
