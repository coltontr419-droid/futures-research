#!/bin/bash
# K15 (decisions.md 795, 799): list, discovery candles, discovery readout; sealed candles + one sealed look only if carried.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k15.done ] && exit 0
[ -f data/kalshi/k15/listed.done ] || { .venv/bin/python -m futuresres.kalshi.k15_nonsports list >> $L/k15.log 2>&1 && touch data/kalshi/k15/listed.done; } || exit 1
[ -f $L/k15_disc.done ] || { .venv/bin/python -m futuresres.kalshi.k15_nonsports candles >> $L/k15.log 2>&1 && .venv/bin/python -m futuresres.kalshi.k15_nonsports >> $L/k15.log 2>&1 && touch $L/k15_disc.done; } || exit 1
grep -q '"carried": true' reports/k15_discovery.json || { touch $L/k15.done; exit 0; }
.venv/bin/python -m futuresres.kalshi.k15_nonsports candles-sealed >> $L/k15.log 2>&1 || exit 1
touch $L/k15.done
