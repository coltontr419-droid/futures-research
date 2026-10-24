#!/bin/bash
cd /home/coltontr419/futures-research && exec .venv/bin/python -m futuresres.stocks.watch_forward >> logs/watchfwd.log 2>&1
