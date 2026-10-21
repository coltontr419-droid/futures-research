#!/bin/bash
# K16 (decisions.md 796, 799): discovery trades of the K15 discovery sample, discovery readout; sealed only if carried.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k16.done ] && exit 0
while [ ! -f $L/k15_disc.done ]; do sleep 60; done
[ -f $L/k16_disc.done ] || { .venv/bin/python -m futuresres.kalshi.k16_makerls download >> $L/k16.log 2>&1 && .venv/bin/python -m futuresres.kalshi.k16_makerls >> $L/k16.log 2>&1 && touch $L/k16_disc.done; } || exit 1
grep -q '"carried": true' reports/k16_discovery.json || { touch $L/k16.done; exit 0; }
touch $L/k16.carried
