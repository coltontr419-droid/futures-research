#!/bin/sh
# 11-15: the three A/B reads for a UID-179 test, back to back (not in parallel: memory), 2 min after the test ends. ≈ 2 min total.
cd /opt/mvtrx
sh abgrp_179.sh $1; sh skillread_179.sh $1; sh makingread_179.sh $1
echo "NOTE $(date +%s) test $1 all reads done: ab_read_$1.txt" >> alerts.txt
