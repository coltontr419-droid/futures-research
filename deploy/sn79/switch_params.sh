#!/bin/sh
# Generic live switch (decisions.md §1207): deploy QuoteAgent.sn.py, move to a new tape, add and/or remove params.
# usage: switch_params.sh <current tape name> <new tape name> "<params to add>" ["<param to remove, e.g. sticky=1>"]
F=/etc/systemd/system/mvtrx-x1.service.d/tape.conf
cp /opt/mvtrx/QuoteAgent.sn.py /opt/mvtrx/agents/QuoteAgent.py
[ -n "$4" ] && sed -i "s# $4##" $F
sed -i "s#tape=/opt/mvtrx/$1.jsonl \(.*\)\$#tape=/opt/mvtrx/$2.jsonl \1 $3#" $F
systemctl daemon-reload && systemctl restart mvtrx-x1
echo "switched $(date -u +%H:%M) UTC: $(grep -o "skew=.*" $F)" >> /opt/mvtrx/switch_live_model.log
