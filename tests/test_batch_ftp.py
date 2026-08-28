"""The batch loader's three promises, tested against a real FTP server.

Resumability and idempotence are properties of an interaction with a server, not of a
function, so they are tested against a real FTP server on localhost rather than a mock. A
mocked socket would confirm that the code calls `retrbinary` with a `rest` argument; it
would not confirm that the resulting file is correct, which is the only thing that matters.

The server is `tests/ftp_stub.py`, a minimal RFC 959 subset written for this purpose —
pyftpdlib has no wheel for this interpreter and fails to build from source, which would
make the suite unrunnable on a fresh checkout.

Two resume paths are covered: a `.part` left behind by an earlier aborted run, and a
connection dropped mid-transfer by the server (`drop_after`), which is what actually happens
on a multi-gigabyte extract.
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from futuresres.data.batch_ftp import (
    BatchFile,
    BatchFTP,
    ManifestUnreadable,
    VerificationFailed,
    _matches,
    _names_from_list,
    parse_manifest,
    sha256_file,
)

from tests.ftp_stub import StubFTPServer

USER, PASSWORD = "tester", "secret"


@pytest.fixture()
def ftp_server(tmp_path: Path):
    """A real FTP server over a temp directory. Yields (host, port, served_dir)."""
    served = tmp_path / "served"
    served.mkdir()
    with StubFTPServer(served, USER, PASSWORD) as server:
        yield server.host, server.port, served


def _client(host: str, port: int) -> BatchFTP:
    client = BatchFTP(host, "/", USER, PASSWORD, timeout=15)
    import ftplib

    ftp = ftplib.FTP(timeout=15)
    ftp.connect(host, port)
    ftp.login(USER, PASSWORD)
    ftp.set_pasv(True)
    ftp.cwd("/")
    ftp.voidcmd("TYPE I")
    client.ftp = ftp
    return client


# ── manifest parsing ─────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_manifest_accepts_a_top_level_list() -> None:
    files = parse_manifest(json.dumps([
        {"filename": "a.dbn.zst", "size": 10, "hash": "sha256:" + "ab" * 32},
    ]))
    assert files == [BatchFile("a.dbn.zst", 10, "ab" * 32)]


@pytest.mark.integrity
def test_manifest_accepts_a_files_key_and_alternative_field_names() -> None:
    files = parse_manifest(json.dumps({"files": [
        {"name": "b.dbn.zst", "size_bytes": 20, "sha256": "CD" * 32},
    ]}))
    assert files == [BatchFile("b.dbn.zst", 20, "cd" * 32)]


@pytest.mark.integrity
def test_manifest_strips_directories_from_filenames() -> None:
    files = parse_manifest(json.dumps([{"path": "sub/dir/c.dbn.zst", "size": 1}]))
    assert files[0].filename == "c.dbn.zst"


@pytest.mark.integrity
def test_a_digest_in_an_algorithm_we_cannot_check_is_discarded_not_trusted() -> None:
    """An md5 recorded as if it were a sha256 would fail every comparison forever."""
    files = parse_manifest(json.dumps([{"filename": "d", "size": 1, "hash": "md5:abcd"}]))
    assert files[0].sha256 is None


@pytest.mark.integrity
@pytest.mark.parametrize("bad", [
    "not json at all",
    json.dumps({"unexpected": "shape"}),
    json.dumps(42),
    json.dumps([]),
    json.dumps([{"size": 1}]),
])
def test_an_unreadable_manifest_raises_rather_than_disabling_verification(bad: str) -> None:
    """The failure mode this guards: silently mirroring with no checking, reporting success."""
    with pytest.raises(ManifestUnreadable):
        parse_manifest(bad)


# ── listing fallback ─────────────────────────────────────────────────────────


@pytest.mark.integrity
def test_list_lines_are_parsed_to_bare_names() -> None:
    lines = [
        "-rw-r--r--   1 owner group     1234 Aug 28 10:00 glbx-mdp3.ohlcv-1m.dbn.zst",
        "-rw-r--r--   1 owner group       97 Aug 28 10:00 manifest.json",
    ]
    assert _names_from_list(lines) == ["glbx-mdp3.ohlcv-1m.dbn.zst", "manifest.json"]


@pytest.mark.integrity
def test_list_remote_finds_files(ftp_server) -> None:
    host, port, served = ftp_server
    (served / "manifest.json").write_text("[]")
    (served / "a.dbn.zst").write_bytes(b"x" * 10)
    client = _client(host, port)
    try:
        assert set(client.list_remote()) == {"manifest.json", "a.dbn.zst"}
    finally:
        client.close()


# ── download: idempotent, resumable, verified ────────────────────────────────


@pytest.mark.integrity
def test_download_then_download_again_is_a_no_op(ftp_server, tmp_path: Path) -> None:
    """IDEMPOTENT: the second run must not transfer a byte."""
    host, port, served = ftp_server
    payload = b"databento" * 5000
    (served / "big.dbn.zst").write_bytes(payload)
    expected = BatchFile("big.dbn.zst", len(payload), hashlib.sha256(payload).hexdigest())
    dest = tmp_path / "dest"

    client = _client(host, port)
    try:
        outcome, moved = client.download("big.dbn.zst", dest, expected)
        assert outcome == "downloaded" and moved == len(payload)
        assert (dest / "big.dbn.zst").read_bytes() == payload

        outcome, moved = client.download("big.dbn.zst", dest, expected)
        assert outcome == "skipped" and moved == 0
    finally:
        client.close()


@pytest.mark.integrity
def test_an_interrupted_transfer_resumes_from_the_partial_file(ftp_server,
                                                               tmp_path: Path) -> None:
    """RESUMABLE: kill the transfer mid-file, re-run, and get a byte-correct result."""
    host, port, served = ftp_server
    payload = bytes(range(256)) * 400          # 102,400 bytes
    (served / "big.dbn.zst").write_bytes(payload)
    expected = BatchFile("big.dbn.zst", len(payload), hashlib.sha256(payload).hexdigest())
    dest = tmp_path / "dest"
    dest.mkdir()

    # Simulate a drop: write the first 30,000 bytes as a .part, as an aborted run would.
    (dest / "big.dbn.zst.part").write_bytes(payload[:30_000])

    client = _client(host, port)
    try:
        outcome, moved = client.download("big.dbn.zst", dest, expected)
        assert outcome == "resumed"
        assert moved == len(payload) - 30_000, "resume re-fetched the whole file"
        assert (dest / "big.dbn.zst").read_bytes() == payload
        assert not (dest / "big.dbn.zst.part").exists()
    finally:
        client.close()


@pytest.mark.integrity
def test_a_partial_file_longer_than_the_remote_is_restarted(ftp_server,
                                                            tmp_path: Path) -> None:
    """A .part from a different, larger file must not be appended to."""
    host, port, served = ftp_server
    payload = b"short payload"
    (served / "f.dbn.zst").write_bytes(payload)
    expected = BatchFile("f.dbn.zst", len(payload), hashlib.sha256(payload).hexdigest())
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "f.dbn.zst.part").write_bytes(b"much longer stale content from another run")

    client = _client(host, port)
    try:
        client.download("f.dbn.zst", dest, expected)
        assert (dest / "f.dbn.zst").read_bytes() == payload
    finally:
        client.close()


@pytest.mark.integrity
def test_a_corrupt_existing_file_is_refetched_not_trusted(ftp_server,
                                                          tmp_path: Path) -> None:
    host, port, served = ftp_server
    payload = b"correct content"
    (served / "g.dbn.zst").write_bytes(payload)
    expected = BatchFile("g.dbn.zst", len(payload), hashlib.sha256(payload).hexdigest())
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "g.dbn.zst").write_bytes(b"WRONG content!!")     # same length, wrong bytes

    client = _client(host, port)
    try:
        outcome, _ = client.download("g.dbn.zst", dest, expected)
        assert outcome == "downloaded"
        assert (dest / "g.dbn.zst").read_bytes() == payload
    finally:
        client.close()


@pytest.mark.integrity
def test_a_hash_mismatch_raises_and_leaves_no_final_file(ftp_server,
                                                         tmp_path: Path) -> None:
    """VERIFIED: a file that fails its hash must not be renamed into place."""
    host, port, served = ftp_server
    (served / "h.dbn.zst").write_bytes(b"actual bytes")
    lying = BatchFile("h.dbn.zst", len(b"actual bytes"), "00" * 32)
    dest = tmp_path / "dest"

    client = _client(host, port)
    try:
        with pytest.raises(VerificationFailed, match="sha256"):
            client.download("h.dbn.zst", dest, lying)
        assert not (dest / "h.dbn.zst").exists(), "unverified file was published"
    finally:
        client.close()


@pytest.mark.integrity
def test_a_size_mismatch_raises(ftp_server, tmp_path: Path) -> None:
    host, port, served = ftp_server
    (served / "i.dbn.zst").write_bytes(b"12345")
    client = _client(host, port)
    try:
        with pytest.raises(VerificationFailed, match="bytes"):
            client.download("i.dbn.zst", tmp_path / "dest", BatchFile("i.dbn.zst", 999))
    finally:
        client.close()


@pytest.mark.integrity
def test_matches_refuses_to_assume_when_there_is_nothing_to_check(tmp_path: Path) -> None:
    """No manifest entry and no SIZE means re-fetch, not 'probably fine'."""
    f = tmp_path / "x"
    f.write_bytes(b"abc")
    assert _matches(f, None, None) is False
    assert _matches(f, BatchFile("x", 3), None) is True
    assert _matches(f, BatchFile("x", None, sha256_file(f)), None) is True


@pytest.mark.integrity
def test_a_connection_dropped_mid_transfer_is_retried_and_completes(tmp_path: Path) -> None:
    """The real failure mode: the server hangs up partway through a large RETR.

    `drop_after` makes the stub send 40,000 bytes and close the data connection without a
    226. The loader must reconnect, REST to what it already has, and finish — and the
    resulting file must be byte-identical, which is the assertion a mock could not make.
    """
    served = tmp_path / "served"
    served.mkdir()
    payload = bytes(range(256)) * 500          # 128,000 bytes
    (served / "huge.dbn.zst").write_bytes(payload)
    expected = BatchFile("huge.dbn.zst", len(payload), hashlib.sha256(payload).hexdigest())
    dest = tmp_path / "dest"

    with StubFTPServer(served, USER, PASSWORD, drop_after=40_000) as server:
        client = BatchFTP(server.host, "/", USER, PASSWORD, timeout=15)
        # reconnect() must target the stub's port, so bind the client to it
        client.connect = lambda: _bind(client, server.host, server.port)   # type: ignore[method-assign]
        client.connect()
        try:
            outcome, _ = client.download("huge.dbn.zst", dest, expected)
        finally:
            client.close()

    assert outcome == "resumed", "the drop did not exercise the resume path"
    assert (dest / "huge.dbn.zst").read_bytes() == payload
    assert not (dest / "huge.dbn.zst.part").exists()


def _bind(client: BatchFTP, host: str, port: int) -> BatchFTP:
    import ftplib

    ftp = ftplib.FTP(timeout=15)
    ftp.connect(host, port)
    ftp.login(USER, PASSWORD)
    ftp.set_pasv(True)
    ftp.cwd("/")
    ftp.voidcmd("TYPE I")
    client.ftp = ftp
    return client
