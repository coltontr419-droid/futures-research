#!/bin/sh
# §1223 add. 4 — run AFTER the user registers hotkey x2 on netuid 79. Two UIDs on ALL 128 books, never trading with each other:
#   x2 = skill-only taker: 10-min fade, 12 bp trigger, 40-min hold, at most one bet per book per sim hour, ≈ $1k clips, no making;
#   x1 = maker on all 128 books, no taking at all; the lock handshake (/opt/mvtrx/locks) keeps x2 out of x1's quotes.
set -e
cd /opt/mvtrx
mkdir -p locks && rm -f locks/*
seq -s " " 0 127 > books_all.txt; : > books_none.txt
cp agents/QuoteAgent.py agents/QuoteAgent.pre-golive.py
cp /opt/mvtrx/QuoteAgent.lock.py agents/QuoteAgent.py.new && mv agents/QuoteAgent.py.new agents/QuoteAgent.py
# x2: skill-only unit (template = the old x2 unit, params replaced)
U=/etc/systemd/system/mvtrx-x2.service; cp $U /opt/mvtrx/mvtrx-x2.service.pre-skill
P="size=0.06 edge=1 model=/opt/mvtrx/agents/model30_of.json tape=/opt/mvtrx/live_tape_x2.jsonl raw=1 lazy_load=1 own_ex=1 skip_file=/opt/mvtrx/books_all.txt sleeve_file=/opt/mvtrx/books_all.txt skip_flat=1 take_size=25 sleeve_bp=12 sleeve_step=3600 sleeve_cool=5 rev_look=600 rev_hold=2400 rev_usd=1000 lock_dir=/opt/mvtrx/locks lock_max=120"
sed -i "s|--agent.params .*|--agent.params $P|; s|^Description=.*|Description=Bittensor SN79 (MVTRX) miner x2, skill-only reversal taker (decisions.md 1223)|" $U
# x1: making on all books, no taking, maker side of the handshake
C=/etc/systemd/system/mvtrx-x1.service.d/tape.conf; cp $C /opt/mvtrx/tape.conf.pre-golive
sed -i "s|skip_file=[^ ]*|skip_file=/opt/mvtrx/books_none.txt|; s| sleeve_file=[^ ]*||; s|skip_flat=1|skip_flat=0|; s|rev_look=[0-9]*|rev_look=0|; s|rev_usd=1000|rev_usd=1000 lock_dir=/opt/mvtrx/locks|" $C
grep -q "lock_dir=/opt/mvtrx/locks" $C
systemctl daemon-reload
systemctl restart mvtrx-x1
systemctl enable --now mvtrx-x2
sleep 60
systemctl is-active mvtrx-x1 mvtrx-x2
echo "x2 params: $(grep -o "agent.params.*" $U)"
echo "x1 params: $(grep -o "agent.params.*" $C)"
