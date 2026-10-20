#!/bin/bash
# K13 download (decisions.md 774-775). Resumable; marks itself done.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k13.done ] && exit 0
.venv/bin/python -m futuresres.kalshi.lean KXLOLGAME KXCS2GAME KXDOTA2GAME KXVALORANTGAME KXR6GAME KXRLGAME KXOWGAME KXCODGAME KXMLBBGAME --start --rate 4 --sample 300 --before 2026-08-20 >> $L/k13_disc.log 2>&1 || exit 1
.venv/bin/python -m futuresres.kalshi.lean KXLOLGAME KXCS2GAME KXDOTA2GAME KXVALORANTGAME KXR6GAME KXRLGAME KXOWGAME KXCODGAME KXMLBBGAME --start --rate 4 --since 2026-08-20 >> $L/k13_seal.log 2>&1 || exit 1
touch $L/k13.done
