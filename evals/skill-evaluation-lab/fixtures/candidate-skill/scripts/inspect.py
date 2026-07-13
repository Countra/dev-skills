"""示例 Skill 的纯函数检查器。"""

from __future__ import annotations


def missing_sections(sections: list[str]) -> list[str]:
    required = {"configuration", "rollback", "validation"}
    return sorted(required - set(sections))
