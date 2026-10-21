#!/bin/bash
# A97 (decisions.md 787): ProphetX +EV offer episodes from the public websocket, indefinitely.
cd /home/coltontr419/futures-research
exec .venv/bin/python -u -m futuresres.sports.a97_pxstream record >> logs/a97.log 2>&1
