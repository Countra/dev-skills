"""严格语义 locator 解析。"""

from __future__ import annotations

from typing import Any

from .errors import VerifierError
from .models import LocatorSpec


def raw_locator(page: Any, spec: LocatorSpec) -> Any:
    if spec.strategy == "role":
        options: dict[str, Any] = {"exact": spec.exact}
        if spec.accessible_name is not None:
            options["name"] = spec.accessible_name
        return page.get_by_role(spec.value, **options)
    if spec.strategy == "label":
        return page.get_by_label(spec.value, exact=spec.exact)
    if spec.strategy == "placeholder":
        return page.get_by_placeholder(spec.value, exact=spec.exact)
    if spec.strategy == "text":
        return page.get_by_text(spec.value, exact=spec.exact)
    if spec.strategy == "testId":
        return page.get_by_test_id(spec.value)
    if spec.strategy == "title":
        return page.get_by_title(spec.value, exact=spec.exact)
    if spec.strategy == "css":
        return page.locator(spec.value)
    raise VerifierError("unsupported_locator", f"不支持的 locator：{spec.strategy}")


async def candidate_summaries(locator: Any, count: int, maximum: int = 10) -> list[dict[str, Any]]:
    summaries = []
    for index in range(min(count, maximum)):
        candidate = locator.nth(index)
        try:
            value = await candidate.evaluate(
                """element => ({
                    tag: element.tagName.toLowerCase(),
                    role: element.getAttribute('role'),
                    name: element.getAttribute('aria-label') || element.innerText || element.value || '',
                    disabled: Boolean(element.disabled) || element.getAttribute('aria-disabled') === 'true'
                })"""
            )
            box = await candidate.bounding_box()
            visible = await candidate.is_visible()
            summaries.append(
                {
                    "index": index,
                    "tag": value.get("tag"),
                    "role": value.get("role"),
                    "nameCharacters": len(str(value.get("name") or "")),
                    "disabled": value.get("disabled") is True,
                    "visible": visible,
                    "boundingBox": box,
                }
            )
        except Exception as exc:
            summaries.append({"index": index, "error": type(exc).__name__})
    return summaries


async def resolve_strict(page: Any, spec: LocatorSpec, *, allow_many: bool = False) -> Any:
    locator = raw_locator(page, spec)
    count = await locator.count()
    if spec.nth is not None:
        if spec.nth >= count:
            raise VerifierError(
                "locator_not_found",
                f"locator.nth={spec.nth} 超出候选范围",
                status=404,
                details={"candidateCount": count},
            )
        return locator.nth(spec.nth)
    if allow_many:
        return locator
    if count == 0:
        raise VerifierError("locator_not_found", "strict locator 未找到候选", status=404)
    if count > 1:
        raise VerifierError(
            "ambiguous_locator",
            "strict locator 匹配多个候选，动作未执行",
            details={"candidateCount": count, "candidates": await candidate_summaries(locator, count)},
        )
    return locator


def locator_risks(spec: LocatorSpec | None) -> list[dict[str, Any]]:
    if spec is None:
        return []
    risks = []
    if spec.strategy == "css":
        risks.append({"code": "css_fallback", "learnable": True})
    if spec.nth is not None:
        risks.append({"code": "explicit_nth", "learnable": False, "nth": spec.nth})
    return risks
