#!/bin/sh
P=https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query
printf "%-34s" gauge; for u in $UIDS; do printf "%12s" "uid $u"; done; echo
for g in $GAUGES; do
  printf "%-34s" $g
  for u in $UIDS; do
    v=$(curl -s -m 20 -G "$P" --data-urlencode "query=max(miner_gauges{miner_gauge_name=\"$g\",agent_id=\"$u\",wallet=~\"5EWwdZB7.*\"})" | python3 -c "import json,sys; r=json.load(sys.stdin)['data']['result']; print(round(float(r[0]['value'][1]),3) if r else 'NA')")
    printf "%12s" "$v"
  done; echo
done
