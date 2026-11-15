#!/bin/sh
# 11-15: apply the REDO settings to a new UID on top of its START (logged switch): sh redo_179.sh <uid>
N=$1; cd /opt/mvtrx
python3 -c "
import json,sys
d = json.load(open(\"live_params_$N.START.json\")); d.update({\"mk_lad_off\": 1, \"mk_gate\": 3, \"mk_gate_side\": 1, \"mk_model_lean\": 1.0, \"mk_model_lean_30\": 1.0, \"mk_lean30_back\": 2, \"fund_mv\": 0.0, \"mk_fade_lean\": 0.0, \"max_inv\": 0.14})
json.dump(d, open(\"live_params_$N.json.tmp\", \"w\"))
" && mv live_params_$N.json.tmp live_params_$N.json
S=$(python3 -c "import json; f=open(\"live_tape_x3.jsonl\",\"rb\"); f.seek(-4000,2); print(int(json.loads(f.read().split(b\"\n\")[-2])[\"ts\"]/1e9))")
echo "$(TZ=America/Chicago date +%T) sim $S A $(cat live_params_$N.json)" >> liveswitch_redo${N}_log.txt
echo "redo applied to UID $N at sim $S"
