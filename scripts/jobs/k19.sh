#!/bin/bash
# K19 (decisions.md 835): fetch trades of the sampled non-sports markets, then the discovery readout. Resumable.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k19.done ] && exit 0
.venv/bin/python -m futuresres.kalshi.k19_whales download >> $L/k19.log 2>&1 || exit 1
.venv/bin/python -m futuresres.kalshi.k19_whales >> $L/k19.log 2>&1
touch $L/k19.done
