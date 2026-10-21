#!/bin/bash
# K17 (decisions.md 797): political race/nomination markets -> daily candles, then the discovery readout. Resumable.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k17.done ] && exit 0
.venv/bin/python -m futuresres.kalshi.k17_politics download >> $L/k17.log 2>&1 || exit 1
.venv/bin/python -m futuresres.kalshi.k17_politics >> $L/k17.log 2>&1
touch $L/k17.done
