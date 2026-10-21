#!/bin/bash
# K18 (decisions.md 821): list settled combos and fetch trades of the samples, then the discovery readout. Resumable.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k18.done ] && exit 0
.venv/bin/python -m futuresres.kalshi.k18_combobuy download >> $L/k18.log 2>&1 || exit 1
.venv/bin/python -m futuresres.kalshi.k18_combobuy >> $L/k18.log 2>&1
touch $L/k18.done
