#!/bin/sh
# Grade each agent script in its task container with the task's own tests (as the Terminal-Bench harness does: /tests, TEST_DIR=/tests).
cd /opt/tb; T=/opt/tb/terminal-bench/original-tasks; G=${GRADES:-grades.txt}; : > $G
for s in ${OUT:-out}/*.sh; do
  t=$(basename $s .sh); img=tbx_$(echo $t | tr A-Z a-z); c=$img-run
  if [ ! -s $s ]; then echo "$t NO_ANSWER" >> $G; continue; fi
  timeout 1800 docker build -q -t $img $T/$t > logs_build_$t.txt 2>&1 || { echo "$t BUILD_FAIL" >> $G; continue; }
  docker rm -f $c >/dev/null 2>&1; docker run -d --name $c $img sh -c "sleep infinity" >/dev/null
  docker cp $s $c:/tmp/solve.sh
  timeout 900 docker exec $c bash /tmp/solve.sh > logs_solve_$t.txt 2>&1; echo "solve exit $?" >> logs_solve_$t.txt
  docker exec $c mkdir -p /tests; docker cp $T/$t/run-tests.sh $c:/tests/run-tests.sh; [ -d $T/$t/tests ] && docker cp $T/$t/tests/. $c:/tests/
  timeout 900 docker exec -e TEST_DIR=/tests $c bash /tests/run-tests.sh > logs_test_$t.txt 2>&1
  line=$(grep -E "[0-9]+ (passed|failed)" logs_test_$t.txt | tail -1)
  if echo "$line" | grep -q "passed" && ! echo "$line" | grep -qE "failed|error"; then r=PASS; else r=FAIL; fi
  echo "$t $r | $line" >> $G
  docker rm -f $c >/dev/null 2>&1
done
echo done > ${GRADES:-grades.txt}.done
