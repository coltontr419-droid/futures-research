cd /opt/mvtrx
A=$(grep " A {" liveswitch_confirm_log.txt | head -1 | sed 's/^[^{]*//')
sh liveswitch_confirm.sh APPLY "$A"
sleep 15
BASE=$(python3 -c 'import json; d=json.load(open("live_params_64.json")); d.pop("mk_dec_inside", None); d.pop("_t", None); print(json.dumps(d)[1:-1])')
sh abtest_sched.sh decin0 "2026-11-11 14:45:00" ABBA "$BASE" '"mk_dec_inside": 0' '"mk_dec_inside": 1' "4-dec: no stepping ahead (UID 46: 12% ahead vs x3 39%) at the same size vs 1 tick ahead"
cat live_params_64.json; echo
md5sum agents/QuoteAgent.py | cut -c1-8
