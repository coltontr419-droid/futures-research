#!/bin/bash
# A99 (decisions.md 804): ProphetX NBA moneyline fair (websocket) vs Kalshi top of book (3 s polls), indefinitely.
cd /home/coltontr419/futures-research
exec .venv/bin/python -u -m futuresres.sports.a99_pxlead record >> logs/a99.log 2>&1
