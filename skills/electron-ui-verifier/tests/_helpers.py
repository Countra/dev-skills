"""electron-ui-verifier 测试共享数据构造器。"""

from __future__ import annotations

import binascii
import struct
import zlib


def _chunk(kind: bytes, payload: bytes) -> bytes:
    checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def make_png(*, solid: bool = False) -> bytes:
    width = 2
    height = 2
    first = bytes((255, 255, 255, 255))
    second = first if solid else bytes((0, 32, 255, 255))
    rows = b"\x00" + first + second + b"\x00" + second + first
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(rows)) + _chunk(b"IEND", b"")
