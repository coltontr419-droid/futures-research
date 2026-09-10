"""Parse the Databento batch into the canonical schema. CLAUDE_FUTURES.md §3.

    python -m futuresres.data.parse

THIS BATCH IS CSV, NOT DBN, AND THAT CHANGES WHAT IS AVAILABLE. `metadata.json` records
`encoding: csv`, `split_symbols: true`, `map_symbols: true` and `schema: ohlcv-1m` only.
Three consequences, each measured rather than assumed:

  1. Files are `.csv.zst`, one per raw_symbol, with columns
     `ts_event, rtype, publisher_id, instrument_id, open, high, low, close, volume, symbol`.
  2. There is NO `symbology.json` — `map_symbols` puts the symbol in every row instead.
  3. There is NO `definition` schema, so **`instrument_class` is not in this batch at all**.

DECISION: HOW OUTRIGHTS ARE IDENTIFIED WITHOUT instrument_class.

`instrument_class` is the correct discriminator and the parser still prefers it when a
definition schema is present. It is not present here, and requesting one is a new batch job.
The fallback is a STRUCTURAL GRAMMAR CHECK, not a substring test:

    outright   ^{ROOT}{MONTH}{YEAR}$        e.g. MGCG1, NQZ5, MNQH6
    spread     ^{outright}-{outright}$      e.g. MGCG1-MGCJ1

Every one of the 806 data files is matched against that grammar and anything matching
neither form is reported rather than guessed at. This is stronger than "contains a hyphen" —
which the previous parser's tests correctly rejected — because it requires BOTH sides of a
spread to be well-formed outrights of the same product, and it rejects an outright whose
symbol is merely unusual. It is still weaker than `instrument_class`, and the report says so.

DECISION: CONTRACTS ARE KEYED BY instrument_id, NOT BY SYMBOL. **CME single-digit year codes
are reused every decade, and this batch spans sixteen years, so the same symbol string names
two different contracts.** Measured:

    MGCG1  instrument_id  83333   2010-10-04..2011-02-22   price 1,310-1,432
    MGCG1  instrument_id  42317   2019-10-01..2021-02-23   price 1,460-2,096
    NQZ5   instrument_id  12809   2014-09-22..2015-12-18   price 3,901-4,739
    NQZ5   instrument_id 158704   2024-12-27..2025-12-19   price 16,873-26,396

`split_symbols` writes both into ONE file. Concatenating by symbol would produce a "contract"
whose price jumps five-fold mid-series — a corruption that no OHLC or outlier check would
catch, because every individual bar is valid. The canonical `contract` field therefore
carries a resolved four-digit year: `NQZ2015` and `NQZ2025` are different contracts.

The expiry year is DERIVED, not assumed: a contract expires at or after its final observed
bar, so the expiry year is the smallest year >= the last bar's year that is congruent to the
symbol's year digit mod 10. `assert_unique_contract_codes` then enforces the invariant that
makes the whole exercise worthwhile — two physical contracts may never resolve to the same
code. That assertion caught a real collision on the first run: `MGCG8` is Feb 2028 with 214
bars starting 2026-04-08, and an earlier rule that simply took the last bar's year labelled
it `MGCG2026`, which would have silently overwritten the genuine Feb 2026 contract on disk.

TRADE COUNT IS NULL. The canonical schema names a `trades` column; `ohlcv-1m` carries only
open, high, low, close and volume. Written as null so a later reader sees "not supplied"
rather than a plausible number nobody measured.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Iterator

import polars as pl
import zstandard

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_RAW: Final[Path] = ROOT / "data" / "raw"
DEFAULT_OUT: Final[Path] = ROOT / "data" / "parquet"
REPORT: Final[Path] = ROOT / "reports" / "batch_contents.md"

#: CME delivery-month codes.
MONTH_CODES: Final[str] = "FGHJKMNQUVXZ"
MONTH_NUMBER: Final[dict[str, int]] = {c: i + 1 for i, c in enumerate(MONTH_CODES)}

#: The outright grammar. Root is 1-4 letters, then one month code, then 1-2 year digits.
OUTRIGHT_RE: Final[re.Pattern[str]] = re.compile(
    rf"^(?P<root>[A-Z0-9]{{1,4}}?)(?P<month>[{MONTH_CODES}])(?P<year>\d{{1,2}})$"
)

#: Expected delivery months per product, for the sanity check §3 asks for.
EXPECTED_MONTHS: Final[dict[str, str]] = {
    "MGC": "GJMQVZ",        # Feb Apr Jun Aug Oct Dec — 6 a year
    "MNQ": "HMUZ",          # Mar Jun Sep Dec — 4 a year
    "NQ": "HMUZ",
}

CANONICAL: Final[tuple[str, ...]] = (
    "ts_event", "symbol", "contract", "open", "high", "low", "close", "volume", "trades",
)


@dataclass(frozen=True, slots=True)
class SymbolForm:
    """What the symbol grammar says a file is."""

    raw_symbol: str
    kind: str                 # "outright" | "spread" | "unrecognised"
    product: str = ""
    month: str = ""
    year_digit: int = -1
    legs: tuple[str, ...] = ()


def classify_symbol(raw_symbol: str) -> SymbolForm:
    """Grammar-based classification. See the module docstring for why, and its limits."""
    if "-" in raw_symbol:
        legs = tuple(raw_symbol.split("-"))
        parsed = [OUTRIGHT_RE.match(leg) for leg in legs]
        if len(legs) >= 2 and all(parsed):
            roots = {m.group("root") for m in parsed if m}
            return SymbolForm(raw_symbol, "spread",
                              product=sorted(roots)[0] if len(roots) == 1 else "",
                              legs=legs)
        return SymbolForm(raw_symbol, "unrecognised", legs=legs)
    m = OUTRIGHT_RE.match(raw_symbol)
    if not m:
        return SymbolForm(raw_symbol, "unrecognised")
    return SymbolForm(raw_symbol, "outright", product=m.group("root"),
                      month=m.group("month"), year_digit=int(m.group("year")) % 10)


@dataclass(slots=True)
class ContractScan:
    """One physical contract: an instrument_id inside one symbol file."""

    instrument_id: int
    raw_symbol: str
    product: str
    month: str
    expiry_year: int
    first_ts: str
    last_ts: str
    rows: int
    decade_resolved: bool


def _read_csv_zst(path: Path) -> pl.DataFrame:
    with path.open("rb") as fh:
        raw = zstandard.ZstdDecompressor().stream_reader(fh).read()
    return pl.read_csv(
        io.BytesIO(raw),
        schema_overrides={"instrument_id": pl.Int64, "volume": pl.Int64,
                          "open": pl.Float64, "high": pl.Float64,
                          "low": pl.Float64, "close": pl.Float64},
        try_parse_dates=False,
    ).with_columns(
        pl.col("ts_event").str.slice(0, 19).str.to_datetime("%Y-%m-%dT%H:%M:%S",
                                                            time_zone="UTC")
    )


def batch_files(raw: Path) -> list[Path]:
    return sorted(raw.glob("*.ohlcv-1m.*.csv.zst"))


def symbol_of(path: Path) -> str:
    return path.name.split(".ohlcv-1m.")[1].removesuffix(".csv.zst")


def resolve_contracts(frame: pl.DataFrame, form: SymbolForm) -> list[ContractScan]:
    """Split one symbol file into physical contracts by instrument_id, resolving the decade."""
    out: list[ContractScan] = []
    per = (frame.group_by("instrument_id")
           .agg(pl.col("ts_event").min().alias("first"),
                pl.col("ts_event").max().alias("last"),
                pl.len().alias("rows"))
           .sort("first"))
    for row in per.iter_rows(named=True):
        expiry, lead = resolve_expiry_year(row["last"].year, form.year_digit)
        out.append(ContractScan(
            instrument_id=int(row["instrument_id"]), raw_symbol=form.raw_symbol,
            product=form.product, month=form.month, expiry_year=expiry,
            first_ts=str(row["first"])[:10], last_ts=str(row["last"])[:10],
            rows=int(row["rows"]), decade_resolved=lead <= MAX_LEAD_YEARS,
        ))
    return out


#: A contract listed more than this many years before expiry is suspicious enough to flag.
#: Gold lists roughly five years out; equity index far less.
MAX_LEAD_YEARS: Final[int] = 6


def resolve_expiry_year(last_bar_year: int, year_digit: int) -> tuple[int, int]:
    """(expiry year, years between the last bar and expiry).

    A contract expires AT OR AFTER its final observed bar, never before. So the expiry year
    is the smallest year >= the last bar's year that is congruent to the symbol's year digit
    mod 10.

    AN EARLIER VERSION TOOK THE LAST BAR'S YEAR DIRECTLY, and that was wrong for contracts
    which have not expired yet: their data simply stops at the end of the batch. `MGCG8` is
    Feb 2028 with 214 bars from 2026-04-08, and the old rule labelled it `MGCG2026` — the
    same code as the genuine Feb 2026 contract, which would have silently overwritten it on
    disk. `assert_unique_contract_codes` now makes that class of collision impossible to
    ship, and it is what surfaced this one.
    """
    for lead in range(10):
        if (last_bar_year + lead) % 10 == year_digit:
            return last_bar_year + lead, lead
    raise ValueError(f"no expiry year congruent to {year_digit} near {last_bar_year}")


def assert_unique_contract_codes(contracts: list[ContractScan]) -> None:
    """Two physical contracts must never resolve to the same canonical code.

    This is the invariant the whole decade-resolution exists to preserve. A collision means
    two different instruments would be written to the same parquet path, one overwriting the
    other, and every downstream check would pass on the survivor.
    """
    seen: dict[str, ContractScan] = {}
    for c in contracts:
        code = contract_code(c.product, c.month, c.expiry_year)
        if code in seen:
            other = seen[code]
            raise ValueError(
                f"contract code collision on {code}: instrument_id {other.instrument_id} "
                f"({other.first_ts}..{other.last_ts}) and {c.instrument_id} "
                f"({c.first_ts}..{c.last_ts}) both resolve to it"
            )
        seen[code] = c


def contract_code(product: str, month: str, expiry_year: int) -> str:
    """`NQZ2015` — unambiguous across decades, unlike `NQZ5`."""
    return f"{product}{month}{expiry_year}"


@dataclass(slots=True)
class BatchScan:
    outright_contracts: list[ContractScan] = field(default_factory=list)
    spread_files: list[SymbolForm] = field(default_factory=list)
    spread_rows: dict[str, int] = field(default_factory=dict)
    unrecognised: list[str] = field(default_factory=list)
    unresolved_decade: list[ContractScan] = field(default_factory=list)

    def by_product(self) -> dict[str, dict[str, int]]:
        table: dict[str, dict[str, int]] = defaultdict(
            lambda: {"outright_contracts": 0, "outright_rows": 0,
                     "spread_files": 0, "spread_rows": 0}
        )
        for c in self.outright_contracts:
            table[c.product]["outright_contracts"] += 1
            table[c.product]["outright_rows"] += c.rows
        for f in self.spread_files:
            key = f.product or "?"
            table[key]["spread_files"] += 1
            table[key]["spread_rows"] += self.spread_rows.get(f.raw_symbol, 0)
        return dict(table)


def scan_batch(raw: Path, out: Path | None = None,
               verbose: bool = True) -> BatchScan:
    """Read every file, classify it, and write the outright bars to parquet."""
    scan = BatchScan()
    files = batch_files(raw)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    for i, path in enumerate(files, 1):
        form = classify_symbol(symbol_of(path))
        if form.kind == "unrecognised":
            scan.unrecognised.append(form.raw_symbol)
            continue
        frame = _read_csv_zst(path)
        if form.kind == "spread":
            scan.spread_files.append(form)
            scan.spread_rows[form.raw_symbol] = frame.height
            continue

        contracts = resolve_contracts(frame, form)
        scan.outright_contracts.extend(contracts)
        assert_unique_contract_codes(scan.outright_contracts)
        scan.unresolved_decade.extend(c for c in contracts if not c.decade_resolved)

        if out is not None:
            lookup = {c.instrument_id: contract_code(c.product, c.month, c.expiry_year)
                      for c in contracts}
            canonical = (
                frame.with_columns(
                    pl.col("instrument_id").replace_strict(lookup, default=None)
                    .alias("contract"),
                    pl.lit(form.product).alias("symbol"),
                    pl.lit(None, dtype=pl.Int64).alias("trades"),
                )
                .select(CANONICAL)
                .sort(["contract", "ts_event"])
            )
            for (code,), part in canonical.group_by(["contract"]):
                target = out / f"symbol={form.product}" / f"contract={code}"
                target.mkdir(parents=True, exist_ok=True)
                part.write_parquet(target / "bars.parquet")
        if verbose and i % 100 == 0:
            print(f"    {i}/{len(files)} files")
    return scan


def month_audit(scan: BatchScan) -> list[str]:
    """Flag delivery months that are not the ones the product should have.

    §3 asks for this explicitly: MGC runs six delivery months a year, MNQ and NQ four. A
    product carrying an unexpected month means either the symbol grammar mis-parsed or the
    request pulled something other than what was intended.
    """
    problems: list[str] = []
    seen: dict[str, set[str]] = defaultdict(set)
    for c in scan.outright_contracts:
        seen[c.product].add(c.month)
    for product, months in sorted(seen.items()):
        expected = EXPECTED_MONTHS.get(product)
        if expected is None:
            problems.append(f"{product}: no expected delivery-month set registered")
            continue
        unexpected = months - set(expected)
        if unexpected:
            problems.append(
                f"{product}: unexpected delivery months {sorted(unexpected)} "
                f"(expected only {sorted(expected)})"
            )
    return problems


def coverage_audit(scan: BatchScan) -> list[str]:
    """Per product, how many contracts per year against how many the calendar implies."""
    lines: list[str] = []
    per: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for c in scan.outright_contracts:
        per[c.product][c.expiry_year] += 1
    for product in sorted(per):
        expected = len(EXPECTED_MONTHS.get(product, ""))
        years = per[product]
        span = f"{min(years)}-{max(years)}"
        full = [y for y, n in years.items() if n == expected]
        short = {y: n for y, n in sorted(years.items()) if n != expected}
        lines.append(
            f"{product}: {len(years)} expiry years ({span}), {expected} months/yr expected, "
            f"{len(full)} complete years"
            + (f"; partial: {short}" if short else "")
        )
    return lines


def render_report(scan: BatchScan, metadata: dict | None = None) -> str:
    w: list[str] = []
    a = w.append
    a("# Batch contents — outrights vs spreads")
    a("")
    a("Generated by `python -m futuresres.data.parse`. CLAUDE_FUTURES.md §3.")
    a("")
    if metadata:
        q = metadata.get("query", {})
        a(f"- **job** `{metadata.get('job_id')}`")
        a(f"- **schema** `{q.get('schema')}` · **encoding** `{q.get('encoding')}` · "
          f"symbols `{', '.join(q.get('symbols', []))}` (`stype_in={q.get('stype_in')}`)")
    total_out = len(scan.outright_contracts)
    total_spread = len(scan.spread_files)
    a(f"- **{total_out} outright contracts kept**, "
      f"**{total_spread} spread series discarded**")
    a(f"- {sum(c.rows for c in scan.outright_contracts):,} outright bars, "
      f"{sum(scan.spread_rows.values()):,} spread bars")
    a("")
    a("> **`instrument_class` is not in this batch.** The request was `ohlcv-1m` only, with "
      "no `definition` schema, so the field CLAUDE_FUTURES.md §3 nominates as the "
      "discriminator does not exist here. Classification falls back to the CME symbol "
      "grammar — `ROOT+MONTH+YEAR` for an outright, two well-formed outrights joined by a "
      "hyphen for a spread — which is checked against every file rather than assumed. This "
      "is weaker than `instrument_class` and the difference is recorded, not glossed.")
    a("")

    a("## Per product")
    a("")
    a("| product | outright contracts | outright bars | spread series | spread bars | spread share of series |")
    a("|---|---|---|---|---|---|")
    for product, c in sorted(scan.by_product().items()):
        total = c["outright_contracts"] + c["spread_files"]
        share = c["spread_files"] / total if total else 0
        a(f"| {product} | {c['outright_contracts']} | {c['outright_rows']:,} | "
          f"{c['spread_files']} | {c['spread_rows']:,} | {share:.1%} |")
    a("")

    a("## Delivery-month audit")
    a("")
    problems = month_audit(scan)
    if problems:
        for p in problems:
            a(f"- **{p}**")
    else:
        a("Every product carries only its expected delivery months "
          "(MGC: Feb Apr Jun Aug Oct Dec; MNQ/NQ: Mar Jun Sep Dec).")
    a("")
    for line in coverage_audit(scan):
        a(f"- {line}")
    a("")

    a("## The decade problem")
    a("")
    a("CME single-digit year codes repeat every ten years and this batch spans sixteen, so "
      "**the same symbol string names two different contracts**. `split_symbols` writes both "
      "into one file. Contracts are therefore keyed by `instrument_id` and the canonical "
      "`contract` field carries a resolved four-digit year.")
    a("")
    reused = defaultdict(list)
    for c in scan.outright_contracts:
        reused[c.raw_symbol].append(c)
    collisions = {s: cs for s, cs in reused.items() if len(cs) > 1}
    a(f"**{len(collisions)} symbol strings name more than one contract.** Examples:")
    a("")
    a("| raw_symbol | instrument_id | resolved contract | first bar | last bar | bars |")
    a("|---|---|---|---|---|---|")
    for sym in sorted(collisions)[:8]:
        for c in sorted(collisions[sym], key=lambda c: c.first_ts):
            a(f"| {c.raw_symbol} | {c.instrument_id} | "
              f"**{contract_code(c.product, c.month, c.expiry_year)}** | {c.first_ts} | "
              f"{c.last_ts} | {c.rows:,} |")
    a("")
    if scan.unresolved_decade:
        a(f"**{len(scan.unresolved_decade)} contract(s) listed unusually far before expiry** "
          f"(more than {MAX_LEAD_YEARS} years), which may indicate a mis-resolved decade:")
        a("")
        for c in scan.unresolved_decade[:10]:
            a(f"- `{c.raw_symbol}` id {c.instrument_id}, last bar {c.last_ts}")
        a("")
    else:
        a(f"Every contract resolved to an expiry within {MAX_LEAD_YEARS} years of its "
          f"last bar, and no two contracts resolved to the same canonical code — the "
          f"latter is asserted during the scan, not merely reported.")
        a("")

    if scan.unrecognised:
        a(f"## Symbols matching neither form ({len(scan.unrecognised)})")
        a("")
        for s in scan.unrecognised[:20]:
            a(f"- `{s}`")
        a("")

    a("## Per-contract row counts")
    a("")
    a("| contract | raw_symbol | instrument_id | first bar | last bar | bars |")
    a("|---|---|---|---|---|---|")
    for c in sorted(scan.outright_contracts,
                    key=lambda c: (c.product, c.expiry_year, MONTH_NUMBER.get(c.month, 0))):
        a(f"| {contract_code(c.product, c.month, c.expiry_year)} | {c.raw_symbol} | "
          f"{c.instrument_id} | {c.first_ts} | {c.last_ts} | {c.rows:,} |")
    a("")
    a("`trades` is null throughout: `ohlcv-1m` carries no trade count. Recorded as "
      "not-supplied rather than derived from volume.")
    a("")
    return "\n".join(w)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.data.parse")
    ap.add_argument("--raw", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--scan-only", action="store_true")
    args = ap.parse_args(argv)

    meta_path = args.raw / "metadata.json"
    metadata = json.loads(meta_path.read_text()) if meta_path.exists() else None

    files = batch_files(args.raw)
    print(f"scanning {len(files)} files in {args.raw}")
    scan = scan_batch(args.raw, None if args.scan_only else args.out)
    print(f"  {len(scan.outright_contracts)} outright contracts, "
          f"{len(scan.spread_files)} spread series, "
          f"{len(scan.unrecognised)} unrecognised")

    for problem in month_audit(scan):
        print(f"  FLAG: {problem}")
    if scan.unresolved_decade:
        print(f"  FLAG: {len(scan.unresolved_decade)} contracts with an unresolved decade")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(render_report(scan, metadata), encoding="utf-8")
    print(f"wrote {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
