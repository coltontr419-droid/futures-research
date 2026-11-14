#!/bin/sh
P=https://taos.simulate.trading/api/datasources/proxy/uid/c7665619-8b04-4227-9882-a44e8dad57a6/api/v1/query
for u in ${UIDS:-174 252 216}; do
  for q in "record:miner_call_time_avg_5m{agent_id=\"$u\"}" "max(miner_gauges{miner_gauge_name=\"call_time_median\",agent_id=\"$u\",wallet=~\"5EWwdZB7.*\"})"; do
    printf "uid %s %s = " "$u" "$(echo $q | cut -c1-34)"; curl -s -m 15 -G "$P" --data-urlencode "query=$q" | python3 -c "import json,sys; r=json.load(sys.stdin)['data']['result']; print([round(float(x['value'][1]),3) for x in r][:4] if r else None)"
  done
done
