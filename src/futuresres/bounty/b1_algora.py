"""B-family 1 (decisions.md 894): Algora open-source bounties — expected value per attempt from closed bounties (GitHub API via gh).

    python -m futuresres.bounty.b1_algora fetch
    python -m futuresres.bounty.b1_algora
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import re
import statistics as st
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "bounty" / "b1.jsonl"


def gh(path: str):
    for k in range(4):
        r = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path], capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout)
        if "rate limit" in r.stderr.lower():
            time.sleep(60)
        else:
            time.sleep(2 ** k)
    return None


def search(q: str) -> list[dict]:
    out = []
    for page in range(1, 11):
        d = gh(f"search/issues?q={q}&per_page=100&page={page}")
        time.sleep(2.5)
        if not d or not d.get("items"):
            break
        out += d["items"]
        if len(out) >= d.get("total_count", 0):
            break
    return out


def amount(issue: dict, comments: list[dict]) -> float | None:
    for lb in issue.get("labels", []):
        m = re.fullmatch(r"\$\s?([\d,]+(?:\.\d+)?)", lb["name"].strip())
        if m:
            return float(m.group(1).replace(",", ""))
    for c in comments:
        if c["user"]["login"].startswith("algora"):
            m = re.search(r"\$\s?([\d,]+(?:\.\d+)?)\s*bounty", c["body"] or "", re.I)
            if m:
                return float(m.group(1).replace(",", ""))
    return None


def fetch() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    done = {json.loads(l)["url"] for l in open(OUT)} if OUT.exists() else set()
    closed = []
    for a, b in (("2026-07-01", "2026-07-31"), ("2026-08-01", "2026-08-31"), ("2026-09-01", "2026-09-30"), ("2026-10-01", "2026-10-20")):
        closed += search(f"label:%22%F0%9F%92%8E+Bounty%22+is:issue+is:closed+closed:{a}..{b}")
    opened = search("label:%22%F0%9F%92%8E+Bounty%22+is:issue+is:open")
    print("closed", len(closed), "open", len(opened), flush=True)
    with open(OUT, "a") as f:
        for i, it in enumerate(closed + opened):
            if it["html_url"] in done:
                continue
            cm = []
            for page in range(1, 6):
                c = gh(it["comments_url"].replace("https://api.github.com/", "") + f"?per_page=100&page={page}") or []
                cm += c
                if len(c) < 100:
                    break
            att = {c["user"]["login"] for c in cm if re.search(r"/attempt\b", c.get("body") or "")}
            claims = {c["user"]["login"] for c in cm if re.search(r"/claim\b", c.get("body") or "")}
            f.write(json.dumps({"url": it["html_url"], "repo": it["repository_url"].split("repos/")[1], "state": it["state"],
                                "created": it["created_at"], "closed": it.get("closed_at"), "labels": [l["name"] for l in it["labels"]],
                                "amount": amount(it, cm), "attempts": len(att), "claims": len(claims), "comments": len(cm),
                                "rewarded": any("rewarded" in l["name"].lower() for l in it["labels"])}) + "\n")
            if i % 50 == 0:
                f.flush(); print(f"  {i}", flush=True)


def readout() -> None:
    R = [json.loads(l) for l in open(OUT)]; C = [r for r in R if r["state"] == "closed" and r["amount"]]; O = [r for r in R if r["state"] == "open" and r["amount"]]
    print(f"closed bounties with an amount {len(C)} (of {sum(r['state'] == 'closed' for r in R)}), open {len(O)}; repos {len({r['repo'] for r in C})}")
    rew = [r for r in C if r["rewarded"]]
    print(f"rewarded {len(rew)} ({len(rew) / max(len(C), 1):.0%}); $ awarded ≈ {sum(r['amount'] for r in rew):,.0f} over 3.7 months "
          f"(≈ ${sum(r['amount'] for r in rew) / 3.7:,.0f}/month platform-wide, this label only)")
    for lo, hi in ((0, 100), (100, 300), (300, 1000), (1000, 1e9)):
        b = [r for r in C if lo <= r["amount"] < hi]; w = [r for r in b if r["rewarded"]]
        if not b:
            continue
        att = sum(max(r["attempts"], 1) for r in b)
        p = len(w) / att if att else 0
        print(f"  ${lo:>4.0f}-{hi if hi < 1e9 else '∞'}: closed {len(b):4}, rewarded {len(w):4}, median attempts {st.median(r['attempts'] for r in b):.0f}, "
              f"P(win|attempt) {p:.1%}, mean $ {st.mean(r['amount'] for r in b):,.0f} → EV/attempt ${p * st.mean(r['amount'] for r in b):,.0f}; "
              f"rewarded/month {len(w) / 3.7:.1f}")
    top = collections.Counter(r["repo"] for r in rew).most_common(10); print("top paying repos:", top)
    print(f"open now: {len(O)} worth ${sum(r['amount'] for r in O):,.0f}; median attempts so far {st.median([r['attempts'] for r in O]) if O else 0}")


if __name__ == "__main__":
    fetch() if sys.argv[1:2] == ["fetch"] else readout()
