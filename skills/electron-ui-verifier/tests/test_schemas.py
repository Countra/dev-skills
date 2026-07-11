"""当前 JSON Schema 集的结构测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from electron_verifier.schema import validate_schema_directory  # noqa: E402


class SchemaTests(unittest.TestCase):
    def test_all_schemas_declare_draft_and_unique_id(self) -> None:
        files = validate_schema_directory(SKILL_ROOT / "schemas")
        self.assertGreaterEqual(len(files), 6)


if __name__ == "__main__":
    unittest.main()
