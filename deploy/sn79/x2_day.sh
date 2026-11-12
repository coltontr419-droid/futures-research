#!/bin/sh
# §1414: x2's 24-h protected test day (user 11-12): 9 INDEPENDENT 2-h ABBA tests back to back, each vs the SAME proven base, then (decided later) a
# confirmation test of all winners, then ≥ 3 h clean on the best setup before protection ends. Only x2's live params file is ever switched. No restarts.
#   sh x2_day.sh <x2 uid> "<first test start UTC, YYYY-mm-dd HH:MM:SS>"
U=$1; T0=$2; cd /opt/mvtrx
[ -n "$U" ] && [ -n "$T0" ] || { echo "usage: x2_day.sh <uid> <start UTC>"; exit 1; }
# per-UID scheduler + edge read
sed "s/live_params_27.json/live_params_$U.json/g; s/us=27 /us=$U /; s/x1 = UID 27/x2 = UID $U/; s/UIDS=\"27 46 216\"/UIDS=\"$U 46 216\"/" abtest_sched_x1.sh > abtest_sched_x2.sh
sed "s/grep -E \" (x1|46) \"/grep -E \" (x2|46) \"/; s/x1 = test subject/x2 = test subject/; s|python3 grpcap.py|UIDS_EXTRA=$U:x2 python3 grpcap.py|" abgrp_x1.sh > abgrp_x2.sh
# base = proven params + the low group decoupled from vol (identical behaviour)
BASE=$(python3 - <<'P'
import json
d = json.load(open("/opt/mvtrx/live_params_27.json")); d.pop("_t", None)
d.update({"book_map": "calm:63-101;low:128-191;dec:192-255", "mk_low_size": 0.022, "mk_low_lad": "1:2:4:7", "mk_low_lad_size": 0.027,
          "mk_dec_touch": 1, "mk_dec_deep2": 0})
print(json.dumps(d))
P
)
echo "$BASE" > live_params_$U.json
echo "x2 base written: live_params_$U.json"
i=0
while IFS="|" read N A B DESC; do
  TS=$(date -u -d "$T0 UTC + $((i * 120)) min" "+%Y-%m-%d %H:%M:%S")
  B0=$(python3 -c "import json,sys; d=json.loads(sys.argv[1]); [d.pop(k, None) for k in sys.argv[2].split(',')]; print(json.dumps(d)[1:-1])" "$BASE" "$(echo "$A" | python3 -c "import json,sys; print(','.join(json.loads('{'+sys.stdin.read().strip()+'}').keys()))")")
  sh abtest_sched_x2.sh x2$N "$TS" ABBA "$B0" "$A" "$B" "x2 day test $((i + 1))/9: $DESC" > /dev/null
  TR=$(date -u -d "$T0 UTC + $((i * 120 + 126)) min" "+%Y-%m-%d %H:%M:%S")
  systemd-run --quiet --unit mvtrx-grp-x2$N --on-calendar "$TR UTC" /bin/sh /opt/mvtrx/abgrp_x2.sh x2$N
  echo "test $((i + 1)) x2$N from $TS UTC"
  i=$((i + 1))
done <<'L'
dec4|"mk_dec_touch": 0, "mk_dec_deep2": 0.6|"mk_dec_touch": 1, "mk_dec_deep2": 0|new 4-dec books deep-only vs touch + one deep
decsz|"mk_dec_size": 0.03|"mk_dec_size": 0.09|4-dec order size $1.5k vs $4.5k (UID 46 trades them small)
decdp|"mk_dec_deep": 0.5|"mk_dec_deep": 0.27|4-dec deep order 0.5 vs 0.27 spreads back
lowsz|"mk_low_size": 0.036|"mk_low_size": 0.022|$30 books touch $1.8k (UID 46) vs $1.1k
lowlad|"mk_low_lad": "1:2:3"|"mk_low_lad": "1:2:4:7"|$30 books ladder 1:2:3 (tick = 3.4 bp) vs 1:2:4:7
lowls|"mk_low_lad_size": 0.045|"mk_low_lad_size": 0.027|$30 books ladder orders larger
vsz|"mk_vol_size": 0.036|"mk_vol_size": 0.022|$300 books touch $1.8k vs $1.1k ($30 books fixed)
calmv|"book_map": "low:128-191;dec:192-255"|"book_map": "calm:63-101;low:128-191;dec:192-255"|books 63-101 on the $300 ladder instead of the calm pattern
skew3|"skew": 3|"skew": 5|inventory lean 3 vs 5
L
