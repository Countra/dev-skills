"""证据质量校验、原子提交和 manifest。"""

from __future__ import annotations

import binascii
import json
import struct
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_bytes, atomic_write_json, resolve_under, sha256_file
from .errors import VerifierError
from .limits import DEFAULT_LIMITS, RuntimeLimits


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class PendingArtifact:
    media_type: str
    data: bytes
    label: str
    extension: str


def _paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def validate_png(data: bytes, *, max_bytes: int = DEFAULT_LIMITS.artifact_bytes) -> dict[str, Any]:
    """校验 PNG 结构、CRC、尺寸、解码和非单色像素。"""

    if len(data) > max_bytes:
        raise VerifierError("screenshot_too_large", "screenshot 超过 artifact 上限")
    if not data.startswith(PNG_SIGNATURE):
        raise VerifierError("invalid_screenshot", "screenshot 缺少 PNG signature")
    offset = len(PNG_SIGNATURE)
    header: tuple[int, int, int, int, int, int, int] | None = None
    compressed = bytearray()
    seen_end = False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        start = offset + 8
        end = start + length
        if end + 4 > len(data):
            raise VerifierError("invalid_screenshot", "PNG chunk 被截断")
        payload = data[start:end]
        expected_crc = struct.unpack(">I", data[end : end + 4])[0]
        actual_crc = binascii.crc32(chunk_type + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise VerifierError("invalid_screenshot", f"PNG {chunk_type.decode('ascii', 'replace')} CRC 无效")
        if chunk_type == b"IHDR":
            if length != 13:
                raise VerifierError("invalid_screenshot", "PNG IHDR 长度无效")
            header = struct.unpack(">IIBBBBB", payload)
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            seen_end = True
            break
        offset = end + 4
    if header is None or not seen_end or not compressed:
        raise VerifierError("invalid_screenshot", "PNG 缺少 IHDR、IDAT 或 IEND")
    width, height, bit_depth, color_type, compression, filtering, interlace = header
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if width < 2 or height < 2 or width > 32768 or height > 32768:
        raise VerifierError("invalid_screenshot", f"PNG 尺寸无效：{width}x{height}")
    if bit_depth != 8 or channels is None or compression != 0 or filtering != 0 or interlace != 0:
        raise VerifierError("unsupported_screenshot", "仅支持 Playwright 生成的 8-bit non-interlaced PNG")
    row_bytes = width * channels
    expected = (row_bytes + 1) * height
    if expected > max_bytes * 4:
        raise VerifierError("screenshot_decode_too_large", "PNG 解码体积超过上限")
    decoder = zlib.decompressobj()
    raw = decoder.decompress(bytes(compressed), expected + 1)
    raw += decoder.flush(max(1, expected + 1 - len(raw)))
    if len(raw) != expected or decoder.unconsumed_tail:
        raise VerifierError("invalid_screenshot", "PNG 解码长度无效")
    previous = bytearray(row_bytes)
    position = 0
    first_pixel: tuple[int, ...] | None = None
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        encoded = raw[position : position + row_bytes]
        position += row_bytes
        decoded = bytearray(row_bytes)
        for index, byte in enumerate(encoded):
            left = decoded[index - channels] if index >= channels else 0
            up = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 0:
                value = byte
            elif filter_type == 1:
                value = byte + left
            elif filter_type == 2:
                value = byte + up
            elif filter_type == 3:
                value = byte + ((left + up) // 2)
            elif filter_type == 4:
                value = byte + _paeth(left, up, upper_left)
            else:
                raise VerifierError("invalid_screenshot", f"PNG filter 无效：{filter_type}")
            decoded[index] = value & 0xFF
        color_channels = 1 if color_type == 0 else 3
        for pixel in range(0, row_bytes, channels):
            current_pixel = tuple(decoded[pixel : pixel + color_channels])
            if first_pixel is None:
                first_pixel = current_pixel
            elif current_pixel != first_pixel:
                variation = max(abs(left - right) for left, right in zip(first_pixel, current_pixel))
                if variation >= 2:
                    return {
                        "width": width,
                        "height": height,
                        "colorType": color_type,
                        "pixelVariation": variation,
                    }
        previous = decoded
    raise VerifierError("blank_screenshot", "screenshot 像素为单色，拒绝登记为证据")


class EvidenceStore:
    def __init__(self, run_dir: Path, limits: RuntimeLimits = DEFAULT_LIMITS) -> None:
        self.run_dir = run_dir
        self.artifacts_dir = run_dir / "artifacts"
        self.manifest_path = run_dir / "evidence-manifest.json"
        self.limits = limits

    def initialize(self, run_id: str) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            atomic_write_json(
                self.manifest_path,
                {"schemaVersion": 1, "runId": run_id, "artifacts": []},
            )

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise VerifierError("evidence_manifest_invalid", f"无法读取 evidence manifest：{exc}", status=500) from exc
        if not isinstance(value, dict) or not isinstance(value.get("artifacts"), list):
            raise VerifierError("evidence_manifest_invalid", "evidence manifest 结构无效", status=500)
        return value

    def commit(self, pending: PendingArtifact, step_id: str) -> dict[str, Any]:
        if not pending.extension.isalnum():
            raise VerifierError("invalid_artifact_extension", "artifact extension 只能包含字母和数字")
        quality = validate_png(pending.data, max_bytes=self.limits.artifact_bytes) if pending.media_type == "image/png" else None
        artifact_id = str(uuid.uuid4())
        name = f"{artifact_id}.{pending.extension.lower()}"
        path = self.artifacts_dir / name
        atomic_write_bytes(path, pending.data, max_bytes=self.limits.artifact_bytes)
        record: dict[str, Any] = {
            "artifactId": artifact_id,
            "stepId": step_id,
            "label": pending.label[:200],
            "path": str(path),
            "mediaType": pending.media_type,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if quality:
            record["quality"] = quality
        manifest = self.load()
        manifest["artifacts"].append(record)
        atomic_write_json(self.manifest_path, manifest)
        return record

    def verify(self) -> list[dict[str, Any]]:
        manifest = self.load()
        verified = []
        for record in manifest["artifacts"]:
            path = resolve_under(self.run_dir, Path(str(record.get("path") or "")), must_exist=True)
            if path.stat().st_size != record.get("bytes") or sha256_file(path) != record.get("sha256"):
                raise VerifierError("evidence_hash_mismatch", f"artifact hash/size 不匹配：{path}", status=500)
            if record.get("mediaType") == "image/png":
                validate_png(path.read_bytes(), max_bytes=self.limits.artifact_bytes)
            verified.append(record)
        return verified
