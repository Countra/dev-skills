"""electron-ui-verifier 测试共享数据构造器。"""

from __future__ import annotations

import binascii
import os
import secrets
import shutil
import struct
import tempfile
import weakref
import zlib
from pathlib import Path


class TestTemporaryDirectory:
    """创建绝对路径且可被 Windows 受限测试身份继续访问的临时目录。"""

    __test__ = False

    def __init__(self, *, dir: str | os.PathLike[str] | None = None) -> None:
        self._delegate = None
        self._finalizer = None
        self._path: Path | None = None
        root = Path(os.path.abspath(dir if dir is not None else tempfile.gettempdir()))
        root.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self._delegate = tempfile.TemporaryDirectory(dir=root)
            self.name = self._delegate.name
            return
        for _ in range(100):
            path = root / f"tmp{secrets.token_hex(8)}"
            try:
                path.mkdir(mode=0o777)
            except FileExistsError:
                continue
            self.name = str(path)
            self._path = path
            self._finalizer = weakref.finalize(self, shutil.rmtree, path, True)
            break
        else:
            raise FileExistsError(f"无法在测试根目录创建唯一临时目录: {root}")

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *_: object) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        delegate = self._delegate
        if delegate is not None:
            delegate.cleanup()
            self._delegate = None
            return
        path = self._path
        if path is None:
            return
        if path.exists():
            shutil.rmtree(path)
        self._path = None
        finalizer = self._finalizer
        if finalizer is not None:
            finalizer.detach()
            self._finalizer = None


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
