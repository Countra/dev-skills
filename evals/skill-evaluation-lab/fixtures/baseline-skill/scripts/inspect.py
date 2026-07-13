"""baseline fixture 的简单检查器。"""


def has_configuration(sections: list[str]) -> bool:
    return "configuration" in sections
