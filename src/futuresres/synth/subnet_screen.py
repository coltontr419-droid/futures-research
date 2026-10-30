"""Screen every Bittensor subnet for automatable mining (decisions.md §1178): per-UID miner pay (p10 / median / p90 in $/month), registration burn,
pool depth, operator concentration (top-5 coldkeys' share of UIDs) and the subnet's on-chain identity. Batched storage reads to respect rate limits.

    python -m futuresres.synth.subnet_screen [tao_usd]
"""

from __future__ import annotations

import collections
import hashlib
import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

from futuresres.synth.chainrpc import compact, rpc, subnet, tx

P = tx(b"SubtensorModule")
OUT = Path(__file__).resolve().parents[3] / "reports" / "subnet_screen.json"


def batch(keys: list[str]) -> dict:
    out = {}
    for i in range(0, len(keys), 128):
        for k in range(5):
            try:
                for ch in rpc("state_queryStorageAt", [keys[i:i + 128]])[0]["changes"]:
                    out[ch[0]] = ch[1]
                break
            except Exception:
                time.sleep(2 * (k + 1))
    return out


def concentration(n: int) -> tuple[int, float]:
    kk = ["0x" + (P + tx(b"Keys") + struct.pack("<H", n) + struct.pack("<H", u)).hex() for u in range(256)]
    hk = batch(kk); hot = [bytes.fromhex(hk[k][2:]) for k in kk if hk.get(k)]
    ok = ["0x" + (P + tx(b"Owner") + hashlib.blake2b(h, digest_size=16).digest() + h).hex() for h in hot]
    ow = batch(ok); c = collections.Counter(ow.get(k) for k in ok)
    tot = sum(c.values()) or 1
    return len(c), sum(v for _, v in c.most_common(5)) / tot


def identity(n: int) -> dict:
    k = struct.pack("<H", n)
    for item in (b"SubnetIdentitiesV3", b"SubnetIdentitiesV2"):
        v = rpc("state_getStorage", ["0x" + (P + tx(item) + hashlib.blake2b(k, digest_size=16).digest() + k).hex()])
        if v:
            b = bytes.fromhex(v[2:]); i = 0; f = []
            for _ in range(8):
                try:
                    L, i = compact(b, i); f.append(b[i:i + L].decode("utf-8", "replace")); i += L
                except Exception:
                    break
            names = ["name", "github", "contact", "url", "discord", "description", "logo", "additional"]
            return dict(zip(names, f))
    return {}


def main(tao: float) -> None:
    rows = []
    for n in range(1, 129):
        try:
            em, vp, burn, price, tempo = subnet(n)
        except Exception:
            continue
        if not em or not price:
            continue
        usd = np.array([e for e, v in zip(em, vp + [0] * len(em)) if not v]) * (7200 / (tempo + 1)) * price * tao * 30
        if len(usd) < 50:
            continue
        p10, p50, p90 = (float(np.percentile(usd, q)) for q in (10, 50, 90))
        if p50 < 80:
            continue
        tao_in = rpc("state_getStorage", ["0x" + (P + tx(b"SubnetTAO") + struct.pack("<H", n)).hex()])
        pool = int.from_bytes(bytes.fromhex(tao_in[2:])[:8], "little") / 1e9 if tao_in else 0.0
        ops, top5 = concentration(n); ident = identity(n)
        rows.append({"netuid": n, "name": ident.get("name", ""), "p10": round(p10), "median": round(p50), "p90": round(p90), "burn_usd": round(burn * tao),
                     "pool_tao": round(pool), "operators": ops, "top5_share": round(top5, 2), "github": ident.get("github", ""),
                     "description": ident.get("description", "")[:160]})
        print(f"SN{n:3} {rows[-1]['name'][:18]:18} p10 ${p10:6,.0f} med ${p50:6,.0f} p90 ${p90:6,.0f} burn ${burn * tao:5,.0f} pool {pool:7,.0f} τ  ops {ops:3} top5 {top5:.0%}", flush=True)
    rows.sort(key=lambda r: -r["median"])
    OUT.write_text(json.dumps(rows, indent=1) + "\n")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 233.0)
