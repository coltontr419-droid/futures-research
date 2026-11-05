#!/bin/sh
# Workspaces at each task's base commit (no .git), readable by the hone user (§1226).
set -e
cd /opt/swe; mkdir -p repos ws
python3 - <<'PY' > /opt/swe/ws.list
import json
for t in json.load(open("/opt/swe/tasks.json")): print(t["instance_id"], t["repo"], t["base_commit"])
PY
while read id repo commit; do
  bare=repos/$(echo $repo | tr / _).git
  [ -d $bare ] || git clone -q --bare https://github.com/$repo $bare
  rm -rf ws/$id && mkdir -p ws/$id
  git --git-dir=$bare archive $commit | tar -x -C ws/$id
  echo "ws $id ok"
done < /opt/swe/ws.list
chown -R hone ws
echo done > prep.done
