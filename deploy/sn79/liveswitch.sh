#!/bin/sh
# §1342: switch a live knob without a restart: write the live-params JSON and log the switch with the current sim s.  liveswitch.sh <label> '<json>'
cd /opt/mvtrx; echo "$2" > live_params_64.json.tmp && mv live_params_64.json.tmp live_params_64.json
S=$(python3 -c "import json; f=open('live_tape_x3.jsonl','rb'); f.seek(-4000,2); print(int(json.loads(f.read().split(b'\n')[-2])['ts']/1e9))")
echo "$(TZ=America/Chicago date +%T) sim $S $1 $2" >> /opt/mvtrx/liveswitch_log.txt
