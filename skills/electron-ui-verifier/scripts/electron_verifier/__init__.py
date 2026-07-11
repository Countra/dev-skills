"""Electron UI verifier 的稳定领域包。"""

from .errors import VerifierError


SCHEMA_VERSION = 1
KNOWLEDGE_FORMAT = "electron-verifier-canonical"

__all__ = ["KNOWLEDGE_FORMAT", "SCHEMA_VERSION", "VerifierError"]
