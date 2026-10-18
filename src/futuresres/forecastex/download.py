"""ForecastEx public data (forecastex-public-data S3): daily prices and every trade (pairs), kept only for the products we study.

    python -m futuresres.forecastex.download [prefixes...]
"""

from __future__ import annotations

import concurrent.futures as cf
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "data" / "forecastex"
BUCKET = "https://forecastex-public-data.s3.amazonaws.com"
KEEP = ("UHLAX_", "UHMDW_", "UHAUS_", "UHMIA_", "UHPHL_", "FFDEC_")


def get(url: str) -> bytes:
    for _ in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research"}), timeout=120).read()
        except Exception:
            pass
    raise RuntimeError(url)


def keys(prefix: str) -> list[str]:
    out, token = [], ""
    while True:
        x = get(f"{BUCKET}/?list-type=2&prefix={prefix}/&max-keys=1000" + (f"&continuation-token={urllib.parse.quote(token)}" if token else "")).decode()
        out += re.findall(r"<Key>([^<]+\.csv)</Key>", x)
        m = re.search(r"<NextContinuationToken>([^<]+)<", x)
        if not m:
            return out
        token = m.group(1)


def one(prefix: str, key: str, keep) -> None:
    dest = OUT / prefix / Path(key).name
    if dest.exists():
        return
    lines = get(f"{BUCKET}/{key}").decode("utf-8", "replace").splitlines()
    rows = [lines[0]] + [ln for ln in lines[1:] if ln.split(",", 2)[1 if prefix == "pairs" else 0].startswith(keep)]
    dest.write_text("\n".join(rows) + "\n")


def main(argv: list[str]) -> int:
    import urllib.parse  # noqa: F401
    for prefix in argv or ["prices", "pairs"]:
        (OUT / prefix).mkdir(parents=True, exist_ok=True)
        ks = keys(prefix)
        with cf.ThreadPoolExecutor(8) as ex:
            for i, _ in enumerate(ex.map(lambda k: one(prefix, k, KEEP), ks)):
                if i % 100 == 0:
                    print(prefix, i, "/", len(ks), flush=True)
        print(prefix, "done", len(ks), flush=True)
    return 0


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main(sys.argv[1:]))
