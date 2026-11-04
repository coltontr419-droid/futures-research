#!/bin/sh
# SN50 Synth forward test (decisions.md §1218): every day, score the last day's REAL prompts with models frozen on 11-04 (no tuning), keep the
# per-prompt rows by date so they add up to the validator's rolling window, and keep the price caches growing (Hyperliquid serves ≈ 17 days).
cd /opt/synth && export PYTHONPATH=src
D=$(date -u +%F); OUT=data/synth/forward/$D; mkdir -p $OUT; LOG=$OUT/run.log
PY=/opt/synth/venv/bin/python
C24="todg_12_144_c_ou20@1.0,todg_12_144_c_vv25_ou40@1.0"
CE="todg_12_36_c_yp@1.0,ses_sp@1.0,ses_sp_yc@1.0"
for a in BTC ETH SOL XRP HYPE; do
  rm -f data/synth/scores_${a}_1.json data/synth/scores1h_${a}_1.json
  echo "== 24h $a" >> $LOG; nice $PY -m futuresres.synth.s50_backtest $a 1 "$C24" >> $LOG 2>&1
  cp data/synth/rows_${a}_1.json $OUT/rows24_${a}.json 2>/dev/null; cp data/synth/scores_${a}_1.json $OUT/scores24_${a}.json 2>/dev/null
  echo "== 1h $a" >> $LOG; nice $PY -m futuresres.synth.s50_1h $a 1 "tod1_120_240" >> $LOG 2>&1
  cp data/synth/bt1h_${a}_1.json $OUT/bt1h_${a}.json 2>/dev/null
done
for a in SP500 AAPLX XAU GOOGLX TSLAX NVDAX WTIOIL SPCX; do
  rm -f data/synth/scores_${a}_1.json
  echo "== ce $a" >> $LOG; nice $PY -m futuresres.synth.s50_backtest $a 1 "$CE" >> $LOG 2>&1
  cp data/synth/rows_${a}_1.json $OUT/rows24_${a}.json 2>/dev/null; cp data/synth/scores_${a}_1.json $OUT/scores24_${a}.json 2>/dev/null
done
for m in $(echo $CE | tr "," " "); do $PY -m futuresres.synth.s50_combined 1 "$m" 0.15 SP500 AAPLX XAU GOOGLX TSLAX NVDAX WTIOIL SPCX >> $OUT/combined.txt 2>&1; done
for m in $(echo $C24 | tr "," " "); do $PY -m futuresres.synth.s50_combined 1 "$m" 0.15 BTC ETH SOL XRP HYPE >> $OUT/combined.txt 2>&1; done
echo "done $(date -u +%H:%M)" >> $LOG
