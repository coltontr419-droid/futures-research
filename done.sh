#!/usr/bin/env bash
# Blocks until no futures-research job is running, then prints a report you can paste back.
#   ./done.sh            wait for whatever is running now
#   ./done.sh -n         report current state and exit immediately
cd "$(dirname "$0")" || exit 1
LOGDIR=${FR_LOGDIR:-/tmp/claude-1000/-home-coltontr419/0c04026c-8e77-48b0-902e-1d4c022a3af5/scratchpad}

jobs_running() { pgrep -af "\.venv/bin/python" | grep -vE "done\.sh|progress\.sh" | grep -q . ; }

if [ "$1" != "-n" ]; then
  if jobs_running; then
    echo "waiting for:"
    pgrep -af "\.venv/bin/python" | grep -vE "done\.sh|progress\.sh" \
      | sed -E 's/.*-m ([a-z_.]+).*/  \1/; s/.*\/([a-z0-9_]+\.py).*/  \1/'
    while jobs_running; do sleep 20; done
  fi
fi

echo
echo "=================== RUN FINISHED  $(date '+%Y-%m-%d %H:%M:%S') ==================="
echo "trials:   $(.venv/bin/python -c "
from pathlib import Path
from futuresres.stats.trials import TrialLog
l=TrialLog(Path('trials.jsonl'))
r=l.verify_chain()
print(f'N={len(l)} chain={\"ok\" if r.ok else \"BROKEN\"}')" 2>/dev/null || echo '?')"
echo "oom kills since boot: $(dmesg 2>/dev/null | grep -c 'Out of memory')"
echo
echo "--- newest 3 logs ---"
for f in $(ls -t "$LOGDIR"/*.log 2>/dev/null | head -3); do
  echo "### $(basename "$f")"
  tail -6 "$f" | sed 's/^/    /'
done
echo
echo "--- new/changed outputs ---"
git status --porcelain reports/ trials.jsonl 2>/dev/null | sed 's/^/    /' | head -12
echo "==================================================================="
