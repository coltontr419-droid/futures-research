#!/bin/sh
# Tag101 m3 overnight bench (decisions.md §1211 add. 13): switch TAG_MODE and the post log, restart, log the switch time.
M=$1
cat > /etc/systemd/system/tag101-m3.service.d/mode.conf <<CONF
[Service]
Environment=TAG_MODE=$M
Environment=TAG_POST_LOG=/opt/tag101/posts_m3_$M.jsonl
CONF
systemctl daemon-reload && systemctl restart tag101-m3
echo "$(date -u +%Y-%m-%dT%H:%M:%S) $M block $(curl -s -H 'Content-Type: application/json' -d '{"id":1,"jsonrpc":"2.0","method":"chain_getHeader","params":[]}' https://entrypoint-finney.opentensor.ai | python3 -c 'import json,sys; print(int(json.load(sys.stdin)["result"]["number"],16))')" >> /opt/tag101/bench_log.txt
