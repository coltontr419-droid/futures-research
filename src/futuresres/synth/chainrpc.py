"""Minimal Bittensor chain reader over public JSON-RPC (no SDK): per-UID emission, validator permits, burn, alpha price, tempo. decisions.md §1164, §1174.
Used by the SN101 earnings logger on the droplet. Needs `xxhash`."""

from __future__ import annotations

import json
import struct
import urllib.request

import xxhash

URL = "https://entrypoint-finney.opentensor.ai"


def tx(s: bytes) -> bytes:
    return xxhash.xxh64_intdigest(s, 0).to_bytes(8, "little") + xxhash.xxh64_intdigest(s, 1).to_bytes(8, "little")


def rpc(method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(URL, body, {"Content-Type": "application/json"}), timeout=60)).get("result")


def raw(item: bytes, netuid: int, pallet: bytes = b"SubtensorModule"):
    v = rpc("state_getStorage", ["0x" + (tx(pallet) + tx(item) + struct.pack("<H", netuid)).hex()])
    return None if v is None else bytes.fromhex(v[2:])


def compact(b: bytes, i: int):
    m = b[i] & 3
    if m == 0:
        return b[i] >> 2, i + 1
    if m == 1:
        return int.from_bytes(b[i:i + 2], "little") >> 2, i + 2
    if m == 2:
        return int.from_bytes(b[i:i + 4], "little") >> 2, i + 4
    n = (b[i] >> 2) + 4
    return int.from_bytes(b[i + 1:i + 1 + n], "little"), i + 1 + n


def vec(b, size: int) -> list[int]:
    if b is None:
        return []
    n, i = compact(b, 0)
    return [int.from_bytes(b[i + k * size:i + (k + 1) * size], "little") for k in range(n)]


def vecbool(b) -> list[int]:
    if b is None:
        return []
    n, i = compact(b, 0)
    return list(b[i:i + n])


def u64(b):
    return None if b is None else int.from_bytes(b[:8], "little")


def subnet(n: int):
    """(emission per UID in alpha per tempo, validator-permit flags, registration burn in TAO, alpha price in TAO, tempo in blocks)."""
    em = [x / 1e9 for x in vec(raw(b"Emission", n), 8)]
    vp = vecbool(raw(b"ValidatorPermit", n))
    burn = u64(raw(b"Burn", n)) or 0
    tao_in, alpha_in = u64(raw(b"SubnetTAO", n)), u64(raw(b"SubnetAlphaIn", n))
    price = tao_in / alpha_in if tao_in and alpha_in else None
    tempo = int.from_bytes(raw(b"Tempo", n) or b"\x68\x01", "little")
    return em, vp, burn / 1e9, price, tempo
