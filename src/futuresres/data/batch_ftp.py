"""Databento batch FTP loader. CLAUDE_FUTURES.md §3, build-order step 4.

    python -m futuresres.data.batch_ftp --dest data/raw

WHAT A BATCH JOB IS, AND WHY THAT SHAPES THIS MODULE. Databento delivers a completed batch
request as a directory of files on FTP: the data itself as `.dbn.zst`, plus support files
describing what was requested and what arrived. It is a fixed deliverable, not a queryable
endpoint — the same request will not be re-run — so this loader treats the remote directory
as an immutable input to be mirrored and verified, never as something to re-derive.

THREE PROPERTIES, AND EACH IS TESTED.

  RESUMABLE   a partial file is continued with REST rather than restarted. These extracts
              run to gigabytes and the connection will drop.
  IDEMPOTENT  a file already present and verified is skipped without touching the network.
              Running this twice must cost nothing the second time.
  VERIFIED    every file is checked against the batch manifest — size and, where the
              manifest provides one, SHA-256.

VERIFICATION NEVER SILENTLY PASSES. If the manifest cannot be parsed, or names a file that
did not arrive, or a hash disagrees, this raises. The crypto project shipped an outlier scan
that reported PASS while scanning zero bars; a verifier that cannot verify must say so
rather than return success. `ManifestUnreadable` exists for exactly that case.

SUPPORT FILES ARE DATA, NOT NOISE. The OHLCV records carry an `instrument_id` integer and
nothing else identifying, so something must map that to a contract. `symbology.json` does
it directly; the `definition` schema does it too and additionally carries
`instrument_class`, which is what separates an outright from a calendar spread.
`metadata.json` records what was actually requested — the only defence against silently
analysing a different date range than intended — and `condition.json` records per-date
availability. All are downloaded, none is filtered, and the run fails if NO identity source
arrived.

This batch has no symbology.json, measured over the control channel; see IDENTITY_SOURCES.

A NOTE ON THE DATA CHANNEL, measured 2026-08-28. The control connection to
`ftp.databento.com:21` authenticates and accepts CWD, but every passive data port it hands
back is unreachable from here — five consecutive PASV commands all returned port 61039 and
all timed out, and active mode (PORT) times out too. The same machine completes a passive
LIST against `ftp.gnu.org` without trouble, so the restriction is specific to this endpoint
rather than to this network. `list_remote` therefore degrades through MLSD -> NLST -> LIST
and, if all three fail, falls back to the manifest, because `SIZE` and `MLST` work on the
control channel alone and can verify files whose names are already known.
"""

from __future__ import annotations

import argparse
import ftplib
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Final, Iterator

ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_DEST: Final[Path] = ROOT / "data" / "raw"
ENV_FILE: Final[Path] = ROOT / ".env"

#: Support files a batch job ships alongside the data. Downloaded first and never filtered.
SUPPORT_FILES: Final[tuple[str, ...]] = (
    "manifest.json", "metadata.json", "symbology.json", "condition.json",
)

#: Identity sources, in preference order. The batch must ship AT LEAST ONE.
#:
#: MEASURED 2026-08-28: this batch has manifest.json (453,439 B), metadata.json (730 B) and
#: condition.json (614,251 B), but NO symbology.json — MLST returns "No such file or
#: directory" for it while succeeding on the other three. Databento omits it for jobs whose
#: request did not need symbol resolution.
#:
#: That is survivable, and an earlier version of this module was wrong to treat symbology as
#: mandatory. The `definition` schema carries `raw_symbol` per instrument_id AND
#: `instrument_class`, so it is both a better identity source and the only source of the
#: field that separates outrights from spreads. symbology.json is the fallback for a batch
#: that ships no definitions — not the other way round.
IDENTITY_SOURCES: Final[tuple[str, ...]] = ("definition", "symbology.json")

CHUNK: Final[int] = 1 << 20


class ManifestUnreadable(RuntimeError):
    """The manifest exists but its shape is not one this loader understands.

    Raised rather than falling back to "no verification", because an unverified mirror that
    reports success is worse than a failed one: it is indistinguishable from a good one.
    """


class VerificationFailed(RuntimeError):
    """A downloaded file disagrees with the manifest."""


@dataclass(frozen=True, slots=True)
class BatchFile:
    """One entry from the manifest."""

    filename: str
    size: int | None = None
    sha256: str | None = None

    @property
    def is_support(self) -> bool:
        return self.filename in SUPPORT_FILES


@dataclass(slots=True)
class FetchResult:
    downloaded: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    bytes_fetched: int = 0

    def summary(self) -> str:
        return (
            f"{len(self.downloaded)} downloaded ({len(self.resumed)} resumed), "
            f"{len(self.skipped)} already present, "
            f"{len(self.verified)} verified, {len(self.unverified)} UNVERIFIED, "
            f"{self.bytes_fetched / 1e6:.1f} MB fetched"
        )


def load_credentials(env_file: Path = ENV_FILE) -> dict[str, str]:
    """Read `.env`. Never logged, never echoed, never written to a report."""
    if not env_file.exists():
        raise FileNotFoundError(
            f"{env_file} not found. Copy .env.example and fill in the Databento "
            f"credentials; it is gitignored."
        )
    out: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    missing = [k for k in ("DATABENTO_FTP_HOST", "DATABENTO_FTP_PATH",
                           "DATABENTO_FTP_USER", "DATABENTO_FTP_PASSWORD")
               if not out.get(k)]
    if missing:
        raise KeyError(f"{env_file} is missing {missing}")
    return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def parse_manifest(raw: bytes | str) -> list[BatchFile]:
    """Parse a batch manifest into BatchFile records.

    Databento's manifest shape is not contractually fixed and has varied across versions, so
    several plausible layouts are accepted: a top-level list, or a dict keyed `files`. Each
    entry may name its size as `size` or `size_bytes`, and its digest as `hash`, `sha256` or
    `checksum`, with or without an algorithm prefix.

    An UNRECOGNISED shape raises. Tolerating layouts is not the same as tolerating failure:
    the point of the manifest is verification, so a manifest that cannot be read must stop
    the run rather than quietly disable the check it exists to perform.
    """
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestUnreadable(f"manifest is not valid JSON: {exc}") from exc

    if isinstance(doc, dict):
        for key in ("files", "manifest", "contents"):
            if isinstance(doc.get(key), list):
                entries = doc[key]
                break
        else:
            raise ManifestUnreadable(
                f"manifest is a JSON object with keys {sorted(doc)[:8]} and none of "
                f"'files'/'manifest'/'contents' holds a list"
            )
    elif isinstance(doc, list):
        entries = doc
    else:
        raise ManifestUnreadable(f"manifest root is {type(doc).__name__}, expected list/dict")

    out: list[BatchFile] = []
    for entry in entries:
        if isinstance(entry, str):
            out.append(BatchFile(entry))
            continue
        if not isinstance(entry, dict):
            raise ManifestUnreadable(f"manifest entry is {type(entry).__name__}")
        name = next((entry[k] for k in ("filename", "name", "file", "path")
                     if entry.get(k)), None)
        if not name:
            raise ManifestUnreadable(f"manifest entry has no filename: {sorted(entry)[:8]}")
        size = next((entry[k] for k in ("size", "size_bytes", "bytes", "length")
                     if isinstance(entry.get(k), int)), None)
        digest = next((entry[k] for k in ("hash", "sha256", "checksum", "digest")
                       if isinstance(entry.get(k), str)), None)
        if digest and ":" in digest:                 # "sha256:abc..."
            algo, _, digest = digest.partition(":")
            if algo.lower().replace("-", "") != "sha256":
                digest = None                        # a digest we cannot check is not one
        out.append(BatchFile(Path(str(name)).name, size, digest.lower() if digest else None))
    if not out:
        raise ManifestUnreadable("manifest parsed but lists no files")
    return out


class BatchFTP:
    """A connection to one batch job's directory."""

    def __init__(self, host: str, path: str, user: str, password: str,
                 timeout: int = 60, passive: bool = True) -> None:
        self.host, self.path, self.user, self.password = host, path, user, password
        self.timeout, self.passive = timeout, passive
        self.ftp: ftplib.FTP | None = None

    # ── connection ────────────────────────────────────────────────────────

    def connect(self) -> "BatchFTP":
        ftp = ftplib.FTP(timeout=self.timeout)
        ftp.connect(self.host, 21)
        ftp.login(self.user, self.password)
        ftp.set_pasv(self.passive)
        ftp.cwd(self.path)
        ftp.voidcmd("TYPE I")
        self.ftp = ftp
        return self

    def close(self) -> None:
        if self.ftp is not None:
            try:
                self.ftp.quit()
            except Exception:
                self.ftp.close()
            self.ftp = None

    def __enter__(self) -> "BatchFTP":
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def _live(self) -> ftplib.FTP:
        if self.ftp is None:
            raise RuntimeError("not connected — use `with BatchFTP(...) as ftp:`")
        return self.ftp

    def reconnect(self) -> None:
        """Re-establish after a dropped transfer, so a resume can continue."""
        self.close()
        self.connect()

    # ── listing, with fallbacks ───────────────────────────────────────────

    def list_remote(self) -> list[str]:
        """Filenames in the batch directory, by whichever method the server allows.

        MLSD, NLST and LIST all need a data connection. Where that is blocked they raise,
        and the caller falls back to the manifest — which is why `size_of` uses SIZE, a
        control-channel command that keeps working when the data channel does not.
        """
        ftp = self._live
        errors: list[str] = []
        try:
            return sorted(name for name, _ in ftp.mlsd() if name not in (".", ".."))
        except Exception as exc:                       # noqa: BLE001 - reported below
            errors.append(f"MLSD: {type(exc).__name__}")
        for command, parse in (("NLST", lambda ls: [Path(x).name for x in ls]),
                               ("LIST", _names_from_list)):
            try:
                lines: list[str] = []
                ftp.retrlines(command, lines.append)
                names = [n for n in parse(lines) if n not in (".", "..")]
                if names:
                    return sorted(names)
            except Exception as exc:                   # noqa: BLE001
                errors.append(f"{command}: {type(exc).__name__}")
        raise ftplib.error_temp(
            "no directory listing available (" + ", ".join(errors) + "). The data channel "
            "is unreachable; fall back to the manifest."
        )

    def size_of(self, name: str) -> int | None:
        """SIZE runs on the CONTROL channel, so it survives a blocked data connection."""
        try:
            return self._live.size(name)
        except Exception:                              # noqa: BLE001
            return None

    def exists(self, name: str) -> bool:
        return self.size_of(name) is not None

    # ── transfer ──────────────────────────────────────────────────────────

    def download(
        self,
        name: str,
        dest_dir: Path,
        expected: BatchFile | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
        max_resumes: int = 5,
    ) -> tuple[str, int]:
        """Fetch one file. Returns (outcome, bytes transferred this call).

        Outcome is "skipped", "downloaded" or "resumed". A `.part` file holds the partial
        transfer and is renamed into place only after verification, so an interrupted run
        can never leave a truncated file that looks complete.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        final = dest_dir / name
        part = dest_dir / f"{name}.part"
        remote_size = (expected.size if expected and expected.size is not None
                       else self.size_of(name))

        if final.exists():
            if _matches(final, expected, remote_size):
                return "skipped", 0
            # Present but wrong: a truncated or corrupt earlier run. Restart it rather than
            # resuming, because a bad prefix cannot be repaired by appending to it.
            final.unlink()

        transferred = 0
        outcome = "downloaded"
        for attempt in range(max_resumes + 1):
            offset = part.stat().st_size if part.exists() else 0
            if offset and remote_size and offset > remote_size:
                part.unlink()                          # local is longer than remote: restart
                offset = 0
            if offset:
                outcome = "resumed"
            if remote_size is not None and offset == remote_size:
                break
            try:
                with part.open("ab" if offset else "wb") as fh:
                    def _write(block: bytes) -> None:
                        nonlocal transferred
                        fh.write(block)
                        transferred += len(block)
                        if on_progress:
                            on_progress(offset + transferred, remote_size)

                    self._live.retrbinary(f"RETR {name}", _write, blocksize=CHUNK,
                                          rest=offset or None)
                break
            except (ftplib.error_temp, ftplib.error_proto, OSError, EOFError):
                if attempt >= max_resumes:
                    raise
                self.reconnect()                       # and loop: offset is re-read from disk

        _verify_or_raise(part, name, expected, remote_size)
        part.replace(final)
        return outcome, transferred


def _names_from_list(lines: list[str]) -> list[str]:
    """Last whitespace-delimited field of a UNIX-style LIST line."""
    out = []
    for line in lines:
        parts = line.split(maxsplit=8)
        if len(parts) >= 9:
            out.append(parts[8])
        elif parts:
            out.append(parts[-1])
    return out


def _matches(path: Path, expected: BatchFile | None, remote_size: int | None) -> bool:
    """Is an existing local file already the file we want?"""
    if expected and expected.sha256:
        return sha256_file(path) == expected.sha256
    size = expected.size if expected and expected.size is not None else remote_size
    if size is None:
        return False            # nothing to check against: re-fetch rather than assume
    return path.stat().st_size == size


def _verify_or_raise(path: Path, name: str, expected: BatchFile | None,
                     remote_size: int | None) -> None:
    size = expected.size if expected and expected.size is not None else remote_size
    if size is not None and path.stat().st_size != size:
        raise VerificationFailed(
            f"{name}: got {path.stat().st_size} bytes, manifest/SIZE says {size}"
        )
    if expected and expected.sha256:
        got = sha256_file(path)
        if got != expected.sha256:
            raise VerificationFailed(
                f"{name}: sha256 {got[:16]}... does not match manifest "
                f"{expected.sha256[:16]}..."
            )


def fetch_batch(
    dest: Path = DEFAULT_DEST,
    env_file: Path = ENV_FILE,
    include: re.Pattern[str] | None = None,
    verbose: bool = True,
) -> FetchResult:
    """Mirror the whole batch directory into `dest`, verified against the manifest."""
    creds = load_credentials(env_file)
    result = FetchResult()

    with BatchFTP(creds["DATABENTO_FTP_HOST"], creds["DATABENTO_FTP_PATH"],
                  creds["DATABENTO_FTP_USER"], creds["DATABENTO_FTP_PASSWORD"]) as ftp:
        # Support files first: the manifest drives everything after it, and symbology is
        # what makes the data interpretable at all.
        absent_support: list[str] = []
        for name in SUPPORT_FILES:
            if not ftp.exists(name):
                absent_support.append(name)
                if verbose:
                    print(f"  (no {name} in this batch)")
                continue
            outcome, moved = ftp.download(name, dest)
            _record(result, name, outcome, moved)
            if verbose:
                print(f"  {outcome:<10} {name}")

        manifest_path = dest / "manifest.json"
        manifest: dict[str, BatchFile] = {}
        if manifest_path.exists():
            manifest = {f.filename: f
                        for f in parse_manifest(manifest_path.read_bytes())}
            if verbose:
                print(f"  manifest lists {len(manifest)} files")

        try:
            remote = ftp.list_remote()
            source = "directory listing"
        except Exception as exc:                       # noqa: BLE001
            if not manifest:
                raise RuntimeError(
                    f"cannot list the batch directory ({exc}) and no manifest is available "
                    f"to enumerate it from. Nothing can be fetched safely."
                ) from exc
            remote = sorted(manifest)
            source = "manifest (directory listing unavailable)"
        if verbose:
            print(f"  {len(remote)} files, from {source}")

        for name in remote:
            if name in SUPPORT_FILES:
                continue
            if include and not include.search(name):
                continue
            expected = manifest.get(name)
            outcome, moved = ftp.download(name, dest, expected)
            _record(result, name, outcome, moved)
            (result.verified if expected and expected.sha256
             else result.unverified).append(name)
            if verbose:
                mark = "verified" if expected and expected.sha256 else "size-only"
                print(f"  {outcome:<10} {name}  [{mark}]")

        # An identity source is not optional: OHLCV records carry an instrument_id and
        # nothing else, so without one the bars cannot be attached to a contract. Either a
        # definition file or symbology.json will do — see IDENTITY_SOURCES.
        has_definitions = any("definition" in n for n in remote)
        has_symbology = "symbology.json" not in absent_support
        if not (has_definitions or has_symbology):
            raise FileNotFoundError(
                "this batch ships neither a `definition` schema nor symbology.json. The "
                "OHLCV records identify instruments by integer id only, so there is no way "
                "to attach a bar to a contract — and no way to tell an outright from a "
                "calendar spread, which needs `instrument_class` from the definitions."
            )
        if verbose and not has_symbology:
            print("  note: no symbology.json; identity comes from the definition schema, "
                  "which also carries the instrument_class needed to filter spreads")

        # A manifest entry that never arrived is a failed mirror, not a partial success.
        if manifest:
            missing = sorted(set(manifest) - set(remote) - set(SUPPORT_FILES))
            if missing:
                raise VerificationFailed(
                    f"manifest lists {len(missing)} file(s) absent from the batch "
                    f"directory: {missing[:5]}"
                )
    return result


def _record(result: FetchResult, name: str, outcome: str, moved: int) -> None:
    result.bytes_fetched += moved
    if outcome == "skipped":
        result.skipped.append(name)
    else:
        result.downloaded.append(name)
        if outcome == "resumed":
            result.resumed.append(name)



# ══════════════════════════════════════════════════════════════════════════════
# LOCAL-DIRECTORY MODE
#
# The batch may already be on disk — downloaded through a browser, or unpacked from the
# .zip Databento also offers. FTP stays the fetch path for when the endpoint is reachable;
# this is the same mirror with the transport removed.
#
# IT RUNS THE SAME VERIFICATION. Copying from a local folder is not a reason to trust it:
# a browser download can truncate, a zip can extract partially, and a file copied from
# Downloads is exactly as unverified as one pulled over FTP. Same manifest, same sizes,
# same SHA-256, same refusal to report success when the manifest cannot be read.
#
# IT COPIES RATHER THAN READING IN PLACE, deliberately. Downloads is not a data directory:
# it is swept by cleanup tools, synced by backup agents, and its contents are not part of
# any reproducible pipeline. Everything downstream reads from `data/raw` so that the input
# to an analysis is somewhere stable and inspectable.
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class LocalVerifyResult:
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    bytes_copied: int = 0

    def summary(self) -> str:
        return (
            f"{len(self.copied)} copied, {len(self.skipped)} already present, "
            f"{len(self.verified)} sha256-verified, {len(self.unverified)} size-only, "
            f"{len(self.missing)} MISSING, {len(self.extra)} not in manifest, "
            f"{self.bytes_copied / 1e6:.1f} MB"
        )


def mirror_local(
    source: Path,
    dest: Path = DEFAULT_DEST,
    verbose: bool = True,
    require_manifest: bool = True,
) -> LocalVerifyResult:
    """Copy a batch directory into `dest`, verified against its own manifest.

    A file already present in `dest` and matching the manifest is left alone, so this is
    idempotent in the same way the FTP path is: running it twice copies nothing the second
    time.
    """
    source, dest = Path(source), Path(dest)
    if not source.is_dir():
        raise NotADirectoryError(f"{source} is not a directory")
    dest.mkdir(parents=True, exist_ok=True)
    result = LocalVerifyResult()

    manifest_src = source / "manifest.json"
    if not manifest_src.exists():
        if require_manifest:
            raise FileNotFoundError(
                f"{manifest_src} not found. Without it nothing can be verified, and an "
                f"unverified mirror that reports success is indistinguishable from a good "
                f"one. Pass require_manifest=False to copy anyway, knowingly."
            )
        manifest: dict[str, BatchFile] = {}
    else:
        manifest = {f.filename: f for f in parse_manifest(manifest_src.read_bytes())}
        if verbose:
            print(f"  manifest lists {len(manifest)} files")

    on_disk = {p.name for p in source.iterdir() if p.is_file()}
    # manifest.json does not list itself; copy it regardless so the mirror is complete.
    wanted = sorted(set(manifest) | (on_disk & set(SUPPORT_FILES)))

    for name in wanted:
        src_file = source / name
        if not src_file.exists():
            result.missing.append(name)
            continue
        expected = manifest.get(name)
        target = dest / name

        if target.exists() and _matches(target, expected, src_file.stat().st_size):
            result.skipped.append(name)
        else:
            part = dest / f"{name}.part"
            with src_file.open("rb") as fin, part.open("wb") as fout:
                for block in iter(lambda: fin.read(CHUNK), b""):
                    fout.write(block)
                    result.bytes_copied += len(block)
            _verify_or_raise(part, name, expected, src_file.stat().st_size)
            part.replace(target)
            result.copied.append(name)

        (result.verified if expected and expected.sha256
         else result.unverified).append(name)

    result.extra = sorted(on_disk - set(wanted))

    if result.missing:
        raise VerificationFailed(
            f"the manifest lists {len(result.missing)} file(s) that are not in {source}: "
            f"{result.missing[:5]}. The extract is incomplete."
        )
    if verbose:
        print(f"  {result.summary()}")
        if result.extra:
            print(f"  note: {len(result.extra)} file(s) present but not in the manifest: "
                  f"{result.extra[:5]}")
    return result

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="futuresres.data.batch_ftp")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    ap.add_argument("--include", type=str, default=None,
                    help="regex; only fetch data files whose name matches")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--from-local", type=Path, default=None,
                    help="mirror an already-downloaded batch directory instead of FTP")
    args = ap.parse_args(argv)

    if args.from_local is not None:
        print(f"Databento batch (local) {args.from_local} -> {args.dest}")
        try:
            local = mirror_local(args.from_local, args.dest, verbose=not args.quiet)
        except Exception as exc:
            print(f"\nFAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(f"\n{local.summary()}")
        return 0

    pattern = re.compile(args.include) if args.include else None
    print(f"Databento batch -> {args.dest}")
    try:
        result = fetch_batch(args.dest, include=pattern, verbose=not args.quiet)
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"\n{result.summary()}")
    if result.unverified:
        print(f"WARNING: {len(result.unverified)} file(s) had no manifest hash and were "
              f"checked on size alone: {result.unverified[:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
