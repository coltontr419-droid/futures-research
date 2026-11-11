cd /opt/mvtrx
sh liveswitch_skew8.sh APPLY "$(cat live_params_64.json)"
A=$(python3 -c 'import json; print(json.dumps(json.load(open("live_params_64.json")))[1:-1])')
python3 - > /tmp/t5b.txt <<'P'
import json
d = json.load(open("/opt/mvtrx/live_params_64.json"))
d.update({"fund": 0, "fund_cap": 0, "fund_scope": 0, "fund_mv": 0, "skew": 5, "mk_vol_touch_min": 0, "mk_vol_inside": 5, "mk_vol_size": 0.034, "mk_vol_lad": "2:5:10:20",
          "mk_vol_lad_size": 0.07, "mk_calm_lad": "1:2:4", "mk_calm_lad_size": 0.036, "mk_dec_inside": 1, "mk_dec_size": 0.09, "mk_dec_deep": 0.27})
print(json.dumps(d)[1:-1])
P
B=$(cat /tmp/t5b.txt)
# A and B carry every key; BASE repeats A's non-differing keys harmlessly (later keys win in JSON? no — avoid duplicates): use an empty base
sh abtest_sched.sh confirm "2026-11-11 12:30:00" ABBA '"_t": 0' "$A" "$B" "all overnight winners (UID 46 quoting on \$300+calm) vs the 9 PM base"
systemctl cat mvtrx-confirm-1.service | grep ExecStart= | tail -1 | cut -c1-420
