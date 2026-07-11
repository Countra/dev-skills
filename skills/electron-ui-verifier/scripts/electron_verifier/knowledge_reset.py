"""旧知识只检测不读取的 fingerprint direct reset gate。"""

from __future__ import annotations

import hmac
import os
import uuid
from pathlib import Path
from typing import Any

from . import KNOWLEDGE_FORMAT, SCHEMA_VERSION
from .atomic_io import canonical_json_bytes, sha256_bytes
from .canonical_store import CanonicalStore, initialize_knowledge_root, knowledge_paths, replace_directory
from .errors import VerifierError


class KnowledgeReset:
    def __init__(self, state_root: Path) -> None:
        self.state_root = state_root.resolve()
        self.root = knowledge_paths(state_root)["root"]

    def _metadata(self) -> list[dict[str, Any]]:
        if not self.root.exists():
            return []
        rows = []
        for current, directories, files in os.walk(self.root, followlinks=False):
            base = Path(current)
            for name in sorted(directories + files):
                path = base / name
                stat = path.lstat()
                rows.append(
                    {
                        "path": path.relative_to(self.root).as_posix(),
                        "kind": "symlink" if path.is_symlink() else ("directory" if path.is_dir() else "file"),
                        "size": stat.st_size,
                        "mtimeNs": stat.st_mtime_ns,
                    }
                )
        return rows

    def classify(self) -> str:
        if not self.root.exists():
            return "absent"
        if not any(self.root.iterdir()):
            return "empty"
        manifest = self.root / "manifest.json"
        if not manifest.is_file():
            return "legacy"
        try:
            import json

            value = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "legacy"
        if value.get("schemaVersion") == SCHEMA_VERSION and value.get("format") == KNOWLEDGE_FORMAT:
            return "current"
        return "legacy"

    def preview(self) -> dict[str, Any]:
        classification = self.classify()
        metadata_digest = sha256_bytes(canonical_json_bytes(self._metadata()))
        normalized_root = os.path.normcase(str(self.root.resolve()))
        fingerprint = sha256_bytes(
            canonical_json_bytes(
                {
                    "operation": "reset-knowledge",
                    "root": normalized_root,
                    "classification": classification,
                    "metadataDigest": metadata_digest,
                    "targetFormat": KNOWLEDGE_FORMAT,
                    "targetSchemaVersion": SCHEMA_VERSION,
                }
            )
        )
        return {
            "classification": classification,
            "root": str(self.root),
            "metadataDigest": metadata_digest,
            "targetFormat": KNOWLEDGE_FORMAT,
            "targetSchemaVersion": SCHEMA_VERSION,
            "confirmationFingerprint": fingerprint,
            "writePerformed": False,
        }

    def ensure(self) -> dict[str, Any]:
        classification = self.classify()
        if classification == "absent":
            initialize_knowledge_root(self.root)
            return {"status": "initialized", "root": str(self.root)}
        if classification == "empty":
            self.root.rmdir()
            initialize_knowledge_root(self.root)
            return {"status": "initialized", "root": str(self.root)}
        if classification == "legacy":
            raise VerifierError(
                "knowledge_reinitialize_required",
                "检测到旧知识布局；新 runtime 不读取、导入或转换该内容",
                status=409,
                details=self.preview(),
            )
        return {"status": "current", "root": str(self.root), "verification": CanonicalStore(self.state_root).verify()}

    def apply(self, confirmation: str) -> dict[str, Any]:
        preview = self.preview()
        expected = str(preview["confirmationFingerprint"])
        if not hmac.compare_digest(expected.encode("utf-8"), confirmation.encode("utf-8")):
            raise VerifierError(
                "knowledge_reset_fingerprint_mismatch",
                "knowledge reset confirmation fingerprint 不匹配",
                status=409,
                details=preview,
            )
        classification = str(preview["classification"])
        retired_path = None
        if classification in {"legacy", "current"}:
            retired_root = self.state_root / "retired"
            retired_root.mkdir(parents=True, exist_ok=True)
            retired_path = retired_root / f"knowledge-{uuid.uuid4()}-{str(preview['metadataDigest'])[:12]}"
            replace_directory(self.root, retired_path)
        elif classification == "empty":
            self.root.rmdir()
        initialize_knowledge_root(self.root)
        return {
            "status": "reset",
            "root": str(self.root),
            "retired": str(retired_path) if retired_path else None,
            "previousClassification": classification,
            "confirmationFingerprint": expected,
            "verification": CanonicalStore(self.state_root).verify(),
        }
