# A141: the Fast Track 100K MNQ day slot by entry time (08:30 / 09:30 / 10:00 / 11:00 / 13:00 ET, flat 16:00), each account ending at its 3rd payout (A135 engine).
# Run: PYTHONPATH=src python scripts/a141_entry_time.py
import futuresres.reporting.y03_sessions as s3
import futuresres.reporting.a08_gold as a8
WIN = {"us_0830_1600": (870, 1320), "rth_0930_1600": (930, 1320), "rth_1000_1600": (960, 1320), "rth_1100_1600": (1020, 1320), "rth_1300_1600": (1140, 1320)}
s3.WINDOWS.update(WIN)
src = open("scripts/a135_three_payout_cap.py").read().split("cases = {")[0]; ns = {}; exec(src, ns)
for w in WIN:
    row = []
    for e in ("pre", "post"):
        h, l, c = a8.era_paths(e, "MNQ", w)[:3]
        v, pp = ns["sim"](h, l, c, 3, 0); row.append(f"{e} {v:+7,.0f} ({pp:.1f}/payout)")
    print(f"{w:14} | " + " | ".join(row), flush=True)
