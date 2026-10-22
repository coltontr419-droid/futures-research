#!/bin/bash
# H2/H3/H4 discovery readouts once H2's daily fetch is complete (decisions.md 853, 855, 856).
cd /home/coltontr419/futures-research
while systemctl --user is-active -q futres-h2 && ! grep -q "discovery:" logs/h2.log; do sleep 60; done
grep -q "discovery:" logs/h2.log || .venv/bin/python -u -m futuresres.stocks.h2_ssr >> logs/h2.log 2>&1
.venv/bin/python -u -m futuresres.stocks.h3_gapdown > logs/h3.log 2>&1
.venv/bin/python -u -m futuresres.stocks.h4_newlistings > logs/h4.log 2>&1
.venv/bin/python -u -m futuresres.stocks.h5_gapup > logs/h5.log 2>&1
