#!/bin/bash
# K16 (decisions.md 796): public trades of the K15 sample, then the discovery readout. Waits for K15's candles. Resumable.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k16.done ] && exit 0
while [ ! -f $L/k15.done ]; do sleep 60; done
.venv/bin/python -m futuresres.kalshi.k16_makerls download >> $L/k16.log 2>&1 || exit 1
.venv/bin/python -m futuresres.kalshi.k16_makerls >> $L/k16.log 2>&1
touch $L/k16.done
