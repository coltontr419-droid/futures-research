"""A minimal FTP server, for testing the batch loader against something real.

WHY NOT A MOCK. Resumability is a property of an interaction — REST offset, a data
connection, a partial file on disk — not of a function call. A mock would confirm that
`retrbinary` was passed a `rest` argument and would happily accept a resume that produced a
corrupt file. This serves real bytes over a real socket so the assertion can be on the
CONTENT of the resumed file.

WHY NOT pyftpdlib. It has no wheel for this interpreter and fails to build from source, so
depending on it would make the test suite unrunnable on a fresh checkout. The subset of
RFC 959 the loader actually uses is small enough to implement here: USER, PASS, TYPE, PWD,
CWD, FEAT, SIZE, REST, RETR, LIST, NLST, MLSD, QUIT.

DELIBERATE OMISSION: no MLSD-less mode switch, no active mode, no TLS. The loader's
fallbacks are exercised by `drop_after` and by the `supports` set rather than by
reimplementing every way a server can be limited.
"""

from __future__ import annotations

import os
import socket
import threading
from pathlib import Path


class StubFTPServer:
    """Serves `root` over FTP on localhost. Use as a context manager."""

    def __init__(self, root: Path, user: str = "tester", password: str = "secret",
                 supports: frozenset[str] | None = None,
                 drop_after: int | None = None) -> None:
        self.root = Path(root)
        self.user, self.password = user, password
        #: Commands the server will honour. Removing one exercises a loader fallback.
        self.supports = supports if supports is not None else frozenset(
            {"MLSD", "LIST", "NLST", "SIZE", "REST"}
        )
        #: Bytes to send on a RETR before hanging up, to simulate a dropped connection.
        self.drop_after = drop_after
        self.drops_remaining = 1 if drop_after else 0

        self._sock = socket.socket()
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.host, self.port = self._sock.getsockname()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def __enter__(self) -> "StubFTPServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._session, args=(conn,), daemon=True).start()

    # ── one client session ────────────────────────────────────────────────

    def _session(self, conn: socket.socket) -> None:
        cwd = "/"
        rest = 0
        data_listener: socket.socket | None = None
        fh = conn.makefile("rwb")
        try:
            self._send(fh, "220 stub FTP ready")
            while True:
                line = fh.readline()
                if not line:
                    return
                raw = line.decode("utf-8", "replace").strip()
                cmd, _, arg = raw.partition(" ")
                cmd = cmd.upper()

                if cmd == "USER":
                    self._send(fh, "331 need password")
                elif cmd == "PASS":
                    self._send(fh, "230 logged in")
                elif cmd in ("TYPE", "NOOP"):
                    self._send(fh, "200 ok")
                elif cmd == "PWD":
                    self._send(fh, f'257 "{cwd}"')
                elif cmd == "CWD":
                    cwd = arg if arg.startswith("/") else f"{cwd.rstrip('/')}/{arg}"
                    self._send(fh, f'250 "{cwd}"')
                elif cmd == "FEAT":
                    feats = "".join(f" {c}\r\n" for c in sorted(self.supports))
                    self._send(fh, f"211-Features:\r\n{feats}211 End", raw=True)
                elif cmd == "SIZE":
                    if "SIZE" not in self.supports:
                        self._send(fh, "502 not implemented")
                    else:
                        target = self._resolve(arg)
                        if target.is_file():
                            self._send(fh, f"213 {target.stat().st_size}")
                        else:
                            self._send(fh, "550 no such file")
                elif cmd == "REST":
                    if "REST" not in self.supports:
                        self._send(fh, "502 not implemented")
                    else:
                        rest = int(arg or 0)
                        self._send(fh, f"350 restarting at {rest}")
                elif cmd == "PASV":
                    data_listener = socket.socket()
                    data_listener.bind(("127.0.0.1", 0))
                    data_listener.listen(1)
                    _, dport = data_listener.getsockname()
                    hi, lo = divmod(dport, 256)
                    self._send(fh, f"227 Entering passive mode (127,0,0,1,{hi},{lo})")
                elif cmd in ("LIST", "NLST", "MLSD"):
                    if cmd not in self.supports or data_listener is None:
                        self._send(fh, "502 not implemented")
                        continue
                    body = self._listing(cmd)
                    self._transfer(fh, data_listener, body.encode())
                    data_listener = None
                elif cmd == "RETR":
                    if data_listener is None:
                        self._send(fh, "425 use PASV first")
                        continue
                    target = self._resolve(arg)
                    if not target.is_file():
                        self._send(fh, "550 no such file")
                        data_listener = None
                        continue
                    payload = target.read_bytes()[rest:]
                    rest = 0
                    truncate = None
                    if self.drops_remaining > 0 and self.drop_after is not None:
                        truncate = self.drop_after
                        self.drops_remaining -= 1
                    self._transfer(fh, data_listener, payload, truncate=truncate)
                    data_listener = None
                elif cmd == "QUIT":
                    self._send(fh, "221 bye")
                    return
                else:
                    self._send(fh, "502 not implemented")
        except (BrokenPipeError, ConnectionResetError, OSError, ValueError):
            return
        finally:
            try:
                fh.close()
                conn.close()
            except OSError:
                pass

    # ── helpers ───────────────────────────────────────────────────────────

    def _resolve(self, name: str) -> Path:
        return self.root / Path(name).name

    def _listing(self, cmd: str) -> str:
        names = sorted(p.name for p in self.root.iterdir() if p.is_file())
        if cmd == "NLST":
            return "".join(f"{n}\r\n" for n in names)
        if cmd == "MLSD":
            return "".join(
                f"type=file;size={(self.root / n).stat().st_size}; {n}\r\n" for n in names
            )
        return "".join(
            f"-rw-r--r-- 1 o g {(self.root / n).stat().st_size:>10} Aug 28 10:00 {n}\r\n"
            for n in names
        )

    def _transfer(self, fh, listener: socket.socket, payload: bytes,
                  truncate: int | None = None) -> None:
        self._send(fh, "150 opening data connection")
        listener.settimeout(10)
        try:
            data, _ = listener.accept()
        except socket.timeout:
            self._send(fh, "425 no data connection")
            listener.close()
            return
        try:
            if truncate is not None:
                # Send a prefix, then hang up mid-stream: a dropped transfer.
                data.sendall(payload[:truncate])
                data.close()
                listener.close()
                self._send(fh, "426 transfer aborted")
                return
            data.sendall(payload)
        finally:
            try:
                data.close()
                listener.close()
            except OSError:
                pass
        self._send(fh, "226 transfer complete")

    @staticmethod
    def _send(fh, message: str, raw: bool = False) -> None:
        fh.write(message.encode() if raw else (message + "\r\n").encode())
        fh.flush()
