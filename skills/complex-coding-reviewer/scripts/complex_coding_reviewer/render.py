"""从已验证 receipt 生成 findings-first Markdown 派生视图。"""

from __future__ import annotations

from typing import Any


SEVERITY_ORDER = {"blocking": 0, "major": 1, "minor": 2, "advisory": 3}
STATUS_ORDER = {"open": 0, "accepted": 1, "deferred": 2, "resolved": 3, "invalidated": 4}


def _location(evidence: dict[str, Any]) -> str:
    if evidence["path"]:
        line = f":{evidence['line']}" if evidence["line"] else ""
        symbol = f" `{evidence['symbol']}`" if evidence["symbol"] else ""
        return f"`{evidence['path']}{line}`{symbol}"
    if evidence["artifact_ref"]:
        return f"artifact `{evidence['artifact_ref']}`"
    if evidence["standard_ref"]:
        return f"standard `{evidence['standard_ref']}`"
    return f"symbol `{evidence['symbol']}`"


def render_receipt(receipt: dict[str, Any]) -> str:
    findings = sorted(
        receipt["findings"],
        key=lambda item: (
            SEVERITY_ORDER[item["severity"]],
            STATUS_ORDER[item["status"]],
            item["id"],
        ),
    )
    lines = [
        f"# Review {receipt['review_id']}",
        "",
        f"- Profile: `{receipt['profile']}`",
        f"- Scope: `{receipt['scope']['kind']}`",
        f"- Verdict: `{receipt['verdict']}`",
        f"- Target SHA-256: `{receipt['target']['digest']}`",
        f"- Context SHA-256: `{receipt['context']['digest']}`",
        f"- Reviewer: `{receipt['reviewer']['mode']}` / `{receipt['reviewer']['identity']}`",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("No findings.")
    for finding in findings:
        lines.extend(
            [
                f"### {finding['id']} [{finding['severity']}] {finding['title']}",
                "",
                f"- Status: `{finding['status']}`",
                f"- Category: `{finding['category']}`",
                f"- Confidence: `{finding['confidence']}`",
                f"- Claim: {finding['claim']}",
                f"- Impact: {finding['impact']}",
                f"- Recommendation: {finding['recommendation']}",
                "- Evidence:",
            ]
        )
        for evidence in finding["evidence"]:
            lines.append(
                f"  - [{evidence['claim_source']}] {_location(evidence)}: {evidence['detail']}"
            )
        origin = finding["origin"]
        if origin["review_id"]:
            lines.append(
                f"- Origin: `{origin['review_id']}` / `{origin['finding_id']}`"
            )
        if finding["disposition_reason"]:
            lines.append(f"- Disposition: {finding['disposition_reason']}")
        lines.append("")
    lines.extend(["## Verification Gaps", ""])
    if not receipt["verification_gaps"]:
        lines.append("No verification gaps.")
    for gap in receipt["verification_gaps"]:
        lines.extend(
            [
                f"- `{gap['id']}` [{gap['severity']}] owner=`{gap['owner']}`: {gap['claim']}",
                f"  Needed evidence: {gap['needed_evidence']}",
            ]
        )
    lines.extend(["", "## Coverage", ""])
    coverage = receipt["coverage"]
    lines.extend(
        [
            f"- Target paths: {len(coverage['target_paths'])}",
            f"- Requirements: {len(coverage['requirement_checks'])}",
            f"- Risk checks: {len(coverage['risk_checks'])}",
            f"- Context expansions: {len(coverage['context_expansions'])}",
        ]
    )
    lines.extend(["", "## Lens Coverage", ""])
    for lens in receipt["lenses"]:
        lines.append(f"- `{lens['id']}` [{lens['status']}]: {lens['summary']}")
    lines.extend(["", "## Evidence-Bound Strengths", ""])
    if not receipt["strengths"]:
        lines.append("No strengths recorded.")
    for strength in receipt["strengths"]:
        lines.append(f"- `{strength['id']}`: {strength['claim']}")
    lines.extend(["", "## Summary", "", receipt["summary"]])
    if receipt["limitations"]:
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in receipt["limitations"])
    return "\n".join(lines) + "\n"
