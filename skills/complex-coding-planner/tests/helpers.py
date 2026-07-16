"""Planner 单测的跨平台可写临时目录。"""

from __future__ import annotations

import os
import shutil
import stat
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_TEMP_ROOT = REPO_ROOT / ".harness" / "test-tmp" / "complex-coding-planner-tests"


class WritableTemporaryDirectory:
    """避免 Windows 私有临时目录 ACL 干扰测试文件访问。"""

    def __init__(self) -> None:
        TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.path = TEST_TEMP_ROOT / f"case-{uuid.uuid4().hex}"
        self.path.mkdir(mode=0o777)
        self.name = str(self.path)

    def cleanup(self) -> None:
        if not self.path.exists():
            return

        def remove_readonly(function, target, _error):
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(self.path, onerror=remove_readonly)
