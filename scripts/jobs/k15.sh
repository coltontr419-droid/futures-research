#!/bin/bash
# K15 (decisions.md 795): list settled non-sports events, then fetch the 24 h candles. Resumable; marks itself done.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k15.done ] && exit 0
[ -f data/kalshi/k15/listed.done ] || { .venv/bin/python -m futuresres.kalshi.k15_nonsports list >> $L/k15.log 2>&1 && touch data/kalshi/k15/listed.done; } || exit 1
.venv/bin/python -m futuresres.kalshi.k15_nonsports candles >> $L/k15.log 2>&1 || exit 1
.venv/bin/python -m futuresres.kalshi.k15_nonsports >> $L/k15.log 2>&1
touch $L/k15.done
