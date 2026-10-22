#!/bin/bash
# V1 (decisions.md 840): EDGAR documents -> Yahoo prices -> readout. Resumable (cached).
cd /home/coltontr419/futures-research; L=logs
[ -f $L/v1.done ] && exit 0
.venv/bin/python -u -m futuresres.stocks.v1_revsplit docs >> $L/v1.log 2>&1 || exit 1
.venv/bin/python -u -m futuresres.stocks.v1_revsplit prices >> $L/v1.log 2>&1 || exit 1
.venv/bin/python -u -m futuresres.stocks.v1_revsplit >> $L/v1.log 2>&1 && touch $L/v1.done
