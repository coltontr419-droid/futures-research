#!/bin/bash
# K11c download (decisions.md 772): discovery sample, then the sealed window. Resumable; marks itself done.
cd /home/coltontr419/futures-research; L=logs
[ -f $L/k11c.done ] && exit 0
.venv/bin/python -m futuresres.kalshi.lean KXNBAPTS KXNBAREB KXNBAAST KXNBA3PT KXWNBAPTS KXMLBHIT KXMLBHR KXMLBKS KXMLBTB KXNHLPTS KXNHLAST KXNHLGOAL KXNFLRSHYDS KXNFLRECYDS KXNFLPASSYDS KXNFLTD --rate 6 --sample 60 --before 2026-08-20 >> $L/k11c_disc.log 2>&1 || exit 1
# sealed data only if discovery carries (decisions.md 772)
.venv/bin/python -m futuresres.kalshi.k11c >> $L/k11c_disc.log 2>&1
grep -q '"carried": true' reports/k11c_discovery.json || { touch $L/k11c.done; exit 0; }
.venv/bin/python -m futuresres.kalshi.lean KXNBAPTS KXNBAREB KXNBAAST KXNBA3PT KXWNBAPTS KXMLBHIT KXMLBHR KXMLBKS KXMLBTB KXNHLPTS KXNHLAST KXNHLGOAL KXNFLRSHYDS KXNFLRECYDS KXNFLPASSYDS KXNFLTD --rate 6 --since 2026-08-20 >> $L/k11c_seal.log 2>&1 || exit 1
touch $L/k11c.done
