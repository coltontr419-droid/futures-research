#!/bin/sh
# SN50 Synth forward test (decisions.md §1218, expanded §1222): every day, score the last day's REAL prompts with frozen models (no tuning),
# keep per-prompt rows + field scores by date for all 3 competitions, and roll every forward day up into $/month per UID (s50_rollup).
#   usage: s50_forward.sh [days] [folder]   (defaults 1 and today's date; the backfill used 2 and <date>-backfill)
cd /opt/synth && export PYTHONPATH=src
N=${1:-1}; D=${2:-$(date -u +%F)}; OUT=data/synth/forward/$D; mkdir -p $OUT; LOG=$OUT/run.log
PY=/opt/synth/venv/bin/python
FAST=todg_12_36_c_ou20@0.95; SLOW=todg_12_144_c_ou20@1.0; VV=todg_12_144_c_vv25_ou40@1.0
C24="$SLOW,$VV,mix:$FAST|$SLOW,mix:$FAST|$SLOW|0.3,mix:$VV|$SLOW,todg_12_36_c_ou20@0.85"   # @0.85: narrower fast model (§1229, SOL ran wide)
CE="todg_12_36_c_yp@1.0,ses_sp@1.0,ses_sp_yc@1.0,ses_sp_yc@1.1,ses_sp_cd20@1.0,mix:todg_12_36_c_yp@1.0|ses_sp_yc@1.0"
C1="tod1_120_240,tod1_30_60_vv25"
for a in BTC ETH SOL XRP HYPE; do
  rm -f data/synth/scores_${a}_$N.json data/synth/scores1h_${a}_$N.json
  echo "== 24h $a" >> $LOG; nice $PY -m futuresres.synth.s50_backtest $a $N "$C24" >> $LOG 2>&1
  cp data/synth/rows_${a}_$N.json $OUT/rows24_${a}.json 2>/dev/null; cp data/synth/scores_${a}_$N.json $OUT/scores24_${a}.json 2>/dev/null
  echo "== 1h $a" >> $LOG; nice $PY -m futuresres.synth.s50_1h $a $N "$C1" >> $LOG 2>&1
  for f in bt1h rows1h scores1h; do cp data/synth/${f}_${a}_$N.json $OUT/${f}_${a}.json 2>/dev/null; done
done
for a in SP500 AAPLX XAU GOOGLX TSLAX NVDAX WTIOIL SPCX; do
  rm -f data/synth/scores_${a}_$N.json
  echo "== ce $a" >> $LOG; nice $PY -m futuresres.synth.s50_backtest $a $N "$CE" >> $LOG 2>&1
  cp data/synth/rows_${a}_$N.json $OUT/rows24_${a}.json 2>/dev/null; cp data/synth/scores_${a}_$N.json $OUT/scores24_${a}.json 2>/dev/null
done
$PY -m futuresres.synth.s50_rollup 53000 > data/synth/forward/rollup.txt 2>&1; cp data/synth/forward/rollup.txt $OUT/rollup.txt
echo "done $(date -u +%H:%M)" >> $LOG
