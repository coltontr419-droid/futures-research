#!/usr/bin/env bash
# Progress of the futures-research data/measurement pipeline.  Usage: ./progress.sh [-w]
LOGDIR=${FR_LOGDIR:-/tmp/claude-1000/-home-coltontr419/0c04026c-8e77-48b0-902e-1d4c022a3af5/scratchpad}
cd "$(dirname "$0")" || exit 1

show() {
  echo "=============== $(date '+%H:%M:%S') ==============="

  # Any python job launched from this repo's venv -- pipeline modules AND ad-hoc probes.
  # Never this script: a plain `pgrep -f futuresres` matches the pattern in its own source,
  # which has produced false "RUNNING" reports more than once.
  running=0
  while read -r pid cmd; do
    [ -z "$pid" ] && continue
    job=$(printf '%s' "$cmd" \
          | sed -E 's/.*-m ([a-z_.]+).*/\1/; s/.*\/([a-z_]+\.py).*/\1/; s/.* -c .*/inline/')
    rss=$(awk '/VmRSS/{printf "%d", $2/1024}' /proc/"$pid"/status 2>/dev/null)
    et=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ')
    printf "RUNNING  %-34s pid %-7s %sMB  elapsed %s\n" "$job" "$pid" "${rss:-?}" "${et:-?}"
    running=1
  done < <(pgrep -af "bin/python (-m |/)" | grep -v progress.sh)
  [ "$running" = 0 ] && echo "  nothing running"

  echo "-- memory --"
  free -m | awk '/Mem:/{printf "  %s MB available of %s MB\n", $7, $2}'

  echo "-- latest log --"
  newest=$(ls -t "$LOGDIR"/*.log 2>/dev/null | head -1)
  [ -n "$newest" ] && { echo "  ($(basename "$newest"))"; tail -3 "$newest" | sed 's/^/  /'; }

  echo "-- continuous series --"
  for f in NQ_MNQ_spliced MGC MNQ NQ; do
    p="data/continuous/$f.parquet"
    [ -f "$p" ] && printf "  %-18s %s\n" "$f" "$(du -h "$p" | cut -f1)" \
                || printf "  %-18s MISSING\n" "$f"
  done

  echo "-- report freshness --"
  for r in reports/level_rates.json reports/placebo_match.md reports/disjointness.md; do
    [ -f "$r" ] && printf "  %-28s %s\n" "$(basename "$r")" "$(date -r "$r" '+%b %d %H:%M')"
  done

  echo "-- recent OOM kills --"
  n=$(dmesg 2>/dev/null | grep -c "Out of memory")
  echo "  ${n:-0} total since boot"
}

if [ "$1" = "-w" ]; then while true; do clear; show; sleep 30; done; else show; fi
