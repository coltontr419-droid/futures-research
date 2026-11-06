#!/bin/sh
# Our UIDs must never trade each other (decisions.md §1240): counts fills where a maker of ours (role "maker" in our_uids.txt) was hit by a
# taker of ours, in the last ~200 MB of x1's tape. Keep /opt/mvtrx/our_uids.txt current: a pruned UID belongs to someone else afterwards.
exec python3 /opt/mvtrx/selftrade.py
