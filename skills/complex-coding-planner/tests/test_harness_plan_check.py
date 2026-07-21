from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

from helpers import WritableTemporaryDirectory


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
REVIEWER_SCRIPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "complex-coding-reviewer"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REVIEWER_SCRIPTS_DIR))

from complex_coding_reviewer.context import RISK_IDS, build_context_target  # noqa: E402
from complex_coding_reviewer.contract import PLAN_LENSES  # noqa: E402
from complex_coding_reviewer.assemble import assemble_receipt  # noqa: E402
from complex_coding_reviewer.dispatch import prepare_dispatch  # noqa: E402
from complex_coding_reviewer.dispatch_lifecycle import finalize_dispatch  # noqa: E402
from complex_coding_reviewer.errors import ReviewError  # noqa: E402
from complex_coding_reviewer.io import resolve_review_ref, sha256_file  # noqa: E402
from complex_coding_reviewer.semantic_result import RECEIPT_SEMANTIC_FIELDS  # noqa: E402
from complex_coding_reviewer.target import build_plan_bundle_target  # noqa: E402
from harness_plan_check import validate_task  # noqa: E402


RESEARCH_GATE_BODY = """- Research result: `not-applicable`
- Decision: 本地事实足以支持 GOAL-01，当前无需在线调研。
- Evidence: REQ-01 与 VAL-01 已形成结构化引用。
- Impact: STG-01 只执行批准范围并保留验证证据。"""


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


PLAN_REVIEW_BRIEF_PATH = "artifacts/reviews/plan-review-brief.json"


def _plan_review_brief(task_dir: Path) -> dict[str, object]:
    contract = json.loads((task_dir / "plan-contract.json").read_text(encoding="utf-8"))
    requirement_refs = [contract["goal"]["id"]]
    for field in ("requirements", "acceptance_criteria", "nonfunctional_requirements"):
        requirement_refs.extend(item["id"] for item in contract[field])
    constraint_refs = [item["id"] for item in contract["stages"]]
    constraint_refs.extend(item["id"] for item in contract["validations"])
    return {
        "profile": "plan-review",
        "scope": {
            "kind": "managed-plan",
            "task_id": contract["task_id"],
            "plan_revision": contract["plan_revision"],
        },
        "summary": "验证当前 managed plan bundle 满足批准与执行要求。",
        "requirement_refs": sorted(requirement_refs),
        "constraint_refs": sorted(constraint_refs),
        "claim_refs": [],
        "requested_risk_focus": [],
        "created_at": "2026-07-16T00:00:00+00:00",
    }


def valid_review_receipt(
    task_dir: Path,
    *,
    review_id: str = "REV-PLAN-001",
    supersedes_review_id: str | None = None,
    extra_context_entries: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    brief = _plan_review_brief(task_dir)
    write_json(task_dir / PLAN_REVIEW_BRIEF_PATH, brief)
    contract = json.loads((task_dir / "plan-contract.json").read_text(encoding="utf-8"))
    policy = "strict" if contract["plan_profile"] == "full" else "conditional"
    delegated = policy == "strict"
    target = build_plan_bundle_target(task_dir)
    identity = target["identity"]
    assert isinstance(identity, dict)
    context_entries = [(PLAN_REVIEW_BRIEF_PATH, "brief")]
    context_entries.extend(
        (str(item["path"]), "requirement")
        for item in target["manifest"]
        if item["state"] == "present" and item["path"] != PLAN_REVIEW_BRIEF_PATH
    )
    context_entries.extend(extra_context_entries or [])
    context = build_context_target(
        task_dir,
        root_kind="task-dir",
        label=f"{review_id.lower()}-context",
        entries=context_entries,
    )
    target_paths = [str(item["path"]) for item in target["manifest"]]
    evidence_ref = PLAN_REVIEW_BRIEF_PATH
    semantic = {
        "kind": "review-semantic-result",
        "review_id": review_id,
        "profile": "plan-review",
        "scope": {
            "kind": "managed-plan",
            "task_id": identity["task_id"],
            "plan_revision": identity["plan_revision"],
        },
        "target_digest": target["digest"],
        "context_digest": context["digest"],
        "standards": [
            {
                "id": "STD-01",
                "title": "Repository rules",
                "source": "AGENTS.md",
                "applicability": "适用于当前 plan bundle。",
            }
        ],
        "coverage": {
            "target_paths": [
                {
                    "path": path,
                    "status": "reviewed",
                    "reason": "fixture 已覆盖完整 plan target。",
                    "gap_ids": [],
                }
                for path in target_paths
            ],
            "requirement_checks": [
                {
                    "id": requirement_ref,
                    "status": "satisfied",
                    "evidence_refs": [evidence_ref],
                    "finding_ids": [],
                    "gap_ids": [],
                    "summary": "当前 plan bundle 提供了可审计证据。",
                }
                for requirement_ref in brief["requirement_refs"]
            ],
            "risk_checks": [
                {
                    "id": risk_id,
                    "status": "not-triggered",
                    "trigger": "fixture 未包含该风险触发面。",
                    "evidence_refs": [evidence_ref],
                    "finding_ids": [],
                    "gap_ids": [],
                    "summary": "已检查触发条件，当前不适用。",
                }
                for risk_id in RISK_IDS
            ],
            "context_expansions": [],
        },
        "lenses": [
            {
                "id": lens,
                "status": "reviewed",
                "evidence_refs": [evidence_ref],
                "summary": f"{lens} 已基于当前 plan bundle 完成审查。",
            }
            for lens in PLAN_LENSES
        ],
        "strengths": [],
        "findings": [],
        "verification_gaps": [],
        "verdict": "passed",
        "open_counts": {
            "blocking": 0,
            "major": 0,
            "minor": 0,
            "advisory": 0,
            "total": 0,
        },
        "summary": "当前 plan bundle 已完成正式方案审查。",
        "limitations": [
            "确定性 fixture 不代表真实子 Agent 观察。"
            if delegated
            else "same-context 不构成独立审查证明。"
        ],
        "supersedes_review_id": supersedes_review_id,
        "reviewed_at": "2026-07-16T00:00:02+00:00",
    }
    review_root = task_dir / "artifacts" / "reviews"
    target_path = review_root / "targets" / f"{review_id}.json"
    context_path = review_root / "contexts" / f"{review_id}.json"
    write_json(target_path, target)
    write_json(context_path, context)
    preparation = prepare_dispatch(
        review_id=review_id,
        target_path=target_path,
        context_path=context_path,
        review_root=review_root,
        policy=policy,
        capability_status="available" if delegated else "policy-disabled",
        tool_family="planner-integration-test",
        available_tools=(
            ["close_agent", "spawn_agent", "wait_agent"] if delegated else []
        ),
        task_dir=task_dir,
        prepared_at="2026-07-16T00:00:00+00:00",
    )
    preparation_path = review_root / "dispatches" / f"{review_id}-prepare.json"
    write_json(preparation_path, preparation)
    if delegated:
        outcome = {
            "status": "completed",
            "agent_id": f"planner-agent-{review_id.lower()}",
            "fork_context": False,
            "started_at": "2026-07-16T00:00:01+00:00",
            "completed_at": "2026-07-16T00:00:02+00:00",
            "schema_repair_count": 0,
            "context_expansion_requested": False,
            "parent_judgment_included": False,
            "recursive_delegation_allowed": False,
            "failure": None,
            "close": {
                "required": True,
                "attempted": True,
                "status": "closed",
                "closed_at": "2026-07-16T00:00:03+00:00",
                "error": None,
            },
            "fallback": {"mode": "none", "reason_code": None, "reason": None},
        }
    else:
        outcome = {
            "status": "fallback",
            "agent_id": None,
            "fork_context": None,
            "started_at": None,
            "completed_at": "2026-07-16T00:00:02+00:00",
            "schema_repair_count": 0,
            "context_expansion_requested": False,
            "parent_judgment_included": False,
            "recursive_delegation_allowed": False,
            "failure": None,
            "close": {
                "required": False,
                "attempted": False,
                "status": "not-required",
                "closed_at": None,
                "error": None,
            },
            "fallback": {
                "mode": "same-context",
                "reason_code": "REVIEW_DISPATCH_POLICY_DISABLED",
                "reason": "低/中风险计划按编排策略执行 same-context 审查。",
            },
        }
    dispatch = finalize_dispatch(
        preparation,
        outcome,
        preparation_path=preparation_path,
        review_root=review_root,
        task_dir=task_dir,
        finalized_at="2026-07-16T00:00:04+00:00",
    )
    dispatch_path = review_root / "dispatches" / f"{review_id}.json"
    result_path = review_root / Path(
        *preparation["inputs"]["semantic_result_ref"].split("/")
    )
    write_json(dispatch_path, dispatch)
    write_json(result_path, semantic)
    return assemble_receipt(
        target_path=target_path,
        context_path=context_path,
        dispatch_path=dispatch_path,
        semantic_result_path=result_path,
        review_root=review_root,
        task_dir=task_dir,
    )


def sync_semantic_result(receipt: dict[str, object], task_dir: Path) -> None:
    """把 receipt 语义修改同步回子 Agent 原始结果并刷新摘要。"""

    review_root = task_dir / "artifacts" / "reviews"
    reviewer = receipt["reviewer"]
    assert isinstance(reviewer, dict)
    result_path = resolve_review_ref(reviewer["semantic_result_ref"], review_root)
    semantic = json.loads(result_path.read_text(encoding="utf-8"))
    for field in RECEIPT_SEMANTIC_FIELDS:
        semantic[field] = receipt[field]
    write_json(result_path, semantic)
    reviewer["semantic_result_digest"] = sha256_file(result_path)


def valid_contract() -> dict[str, object]:
    return {
        "task_id": "test-task",
        "plan_revision": 1,
        "lifecycle_route": "managed",
        "plan_profile": "lite",
        "goal": {"id": "GOAL-01", "summary": "交付可观察结果"},
        "requirements": [{"id": "REQ-01", "priority": "must", "summary": "实现需求"}],
        "acceptance_criteria": [
            {"id": "AC-01", "requirement_ids": ["REQ-01"], "summary": "Given 输入 When 执行 Then 成功"}
        ],
        "nonfunctional_requirements": [{"id": "NFR-01", "summary": "保持可维护性"}],
        "artifacts": [
            {
                "id": "ART-01",
                "kind": "review",
                "path": "artifacts/reviews/plan-review-attempt-1.json",
                "required": True,
                "approval_included": True,
            },
            {
                "id": "ART-09",
                "kind": "other",
                "path": PLAN_REVIEW_BRIEF_PATH,
                "required": True,
                "approval_included": True,
            },
        ],
        "stages": [
            {
                "id": "STG-01",
                "title": "实现并验证",
                "depends_on": [],
                "requirement_ids": ["REQ-01"],
                "acceptance_ids": ["AC-01"],
                "nonfunctional_ids": ["NFR-01"],
                "validation_ids": ["VAL-01"],
                "allowed_changes": ["src/"],
                "forbidden_changes": ["unrelated/"],
                "entry_conditions": ["plan approved"],
                "exit_conditions": ["tests pass"],
                "risk": "low",
                "commit_expectation": "final",
            }
        ],
        "validations": [
            {
                "id": "VAL-01",
                "kind": "test",
                "required": True,
                "covers": ["AC-01", "NFR-01"],
                "command": "python -m unittest",
                "evidence_path": "artifacts/validation/tests.md",
            }
        ],
        "dependency_selection": {
            "mode": "none",
            "necessity_result": "not-triggered",
            "decision_ids": [],
            "evidence_artifact_ids": [],
            "decisions": [],
        },
        "research": {"mode": "local-only", "evidence_artifact_ids": [], "unresolved": []},
        "approval_policy": {
            "implementation_requires_user_approval": True,
            "commit_requires_explicit_authorization": True,
            "external_write_requires_explicit_authorization": True,
            "elevated_tool_requires_explicit_authorization": True,
        },
        "reapproval_triggers": ["scope changes"],
        "stop_conditions": ["user requests pause"],
    }


def valid_plan(extra: str = "") -> str:
    headings = [
        "规划摘要",
        "问题定义",
        "需求与验收",
        "调研门禁",
        "依赖选型门禁",
        "规范发现门禁",
        "开发质量门禁",
        "上下文",
        "候选方案",
        "决策",
        "影响面矩阵",
        "实施计划",
        "环境",
        "Git 上下文",
        "工具",
        "长期进程管理",
        "验证",
        "文档",
        "文件写入策略",
        "方案质量门禁",
        "正式方案审查",
        "就绪门禁",
        "方案批准",
        "方案变更门禁",
        "Artifact Index",
        "Executor Handoff",
    ]
    sections: list[str] = ["# Test Plan"]
    gate_bodies = {
        "调研门禁": RESEARCH_GATE_BODY,
        "依赖选型门禁": (
            "- Selection mode: `none`\n"
            "- Dependency selection result: `not-applicable`"
        ),
        "规范发现门禁": (
            "- Standards result: `passed`\n"
            "- Decision: 采用当前项目 Python 与 closed JSON 规范。\n"
            "- Evidence: REQ-01、STG-01 与仓库规则。\n"
            "- Impact: VAL-01 验证结构和实现质量。"
        ),
        "开发质量门禁": (
            "- Development quality result: `passed`\n"
            "- Decision: 保持单模块职责和最小耦合。\n"
            "- Evidence: STG-01 的 scope 与 VAL-01。\n"
            "- Impact: review 检查静态质量和架构边界。"
        ),
        "方案质量门禁": (
            "- Quality result: `passed`\n"
            "- Decision: 需求、阶段和验证已经闭环。\n"
            "- Evidence: REQ-01、AC-01、STG-01、VAL-01。\n"
            "- Impact: 批准后可以确定性执行。"
        ),
        "正式方案审查": (
            "- Profile: `plan-review`\n"
            "- Scope: `managed-plan`\n"
            "- Coordinator: `review-coordinator`\n"
            "- Dispatch: `complex-coding-reviewer/scripts/review_dispatch.py`\n"
            "- Expected dispatch policy: `conditional`\n"
            "- Current receipt: `artifacts/reviews/plan-review-attempt-1.json`\n"
            "- Validator: `complex-coding-reviewer/scripts/review_validate.py`\n"
            "- Canonical result: JSON receipt only."
        ),
        "就绪门禁": (
            "- Readiness result: `ready_for_review`\n"
            "- Decision: 工具、范围和授权请求已稳定，可以交给 Reviewer。\n"
            "- Evidence: STG-01、VAL-01 与 approval policy。\n"
            "- Impact: 只启动 formal plan-review，不提前请求实施。"
        ),
    }
    for heading in headings:
        body = gate_bodies.get(heading, "complete")
        if heading == "规划摘要":
            body = (
                "Task ID: test-task\n\n"
                "Plan revision: 1\n\n"
                "Lifecycle route: managed\n\n"
                "Plan profile: lite"
            )
        elif heading == "问题定义":
            body = "GOAL-01"
        elif heading == "需求与验收":
            body = "REQ-01 AC-01 NFR-01"
        elif heading == "候选方案":
            body = "### 方案 A\n最小改动\n\n### 方案 B\n结构化改动"
        elif heading == "实施计划":
            body = (
                "### STG-01：实现并验证\n"
                "REQ-01 AC-01 NFR-01 VAL-01 src/ unrelated/"
            )
        elif heading == "Artifact Index":
            body = (
                "ART-01 artifacts/reviews/plan-review-attempt-1.json "
                f"ART-09 {PLAN_REVIEW_BRIEF_PATH}"
            )
        sections.append(f"## {heading}\n\n{body}")
    sections.append(extra)
    return "\n\n".join(sections) + "\n"


def compact_plan() -> str:
    plan = valid_plan()
    groups = [
        (["问题定义", "需求与验收"], "问题定义与需求与验收"),
        (
            ["调研门禁", "依赖选型门禁", "规范发现门禁", "开发质量门禁"],
            "调研门禁、依赖选型门禁、规范发现门禁与开发质量门禁",
        ),
        (
            ["上下文", "候选方案", "决策", "影响面矩阵"],
            "上下文、候选方案、决策与影响面矩阵",
        ),
        (
            ["环境", "Git 上下文", "工具", "长期进程管理"],
            "环境、Git、工具与长期进程",
        ),
        (["验证", "文档"], "验证与文档"),
        (["文件写入策略"], "文件写入策略与问题覆盖"),
        (["方案质量门禁", "正式方案审查"], "方案质量门禁与正式方案审查"),
        (
            ["就绪门禁", "方案批准", "方案变更门禁"],
            "就绪门禁、方案批准与方案变更门禁",
        ),
    ]
    for headings, combined in groups:
        plan = plan.replace(f"## {headings[0]}\n", f"## {combined}\n", 1)
        for heading in headings[1:]:
            plan = plan.replace(f"\n\n## {heading}\n\n", "\n\n", 1)
    return plan


class PlannerBundleTest(unittest.TestCase):
    def make_task(self, contract: dict[str, object] | None = None, plan: str | None = None) -> Path:
        temp = WritableTemporaryDirectory()
        self.addCleanup(temp.cleanup)
        task_dir = Path(temp.name)
        (task_dir / "plan-contract.json").write_text(
            json.dumps(contract or valid_contract(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (task_dir / "execution-plan.md").write_text(plan or valid_plan(), encoding="utf-8")
        self.write_current_review(task_dir)
        return task_dir

    def write_current_review(
        self,
        task_dir: Path,
        *,
        review_id: str = "REV-PLAN-001",
        supersedes_review_id: str | None = None,
    ) -> Path | None:
        contract = json.loads((task_dir / "plan-contract.json").read_text(encoding="utf-8"))
        reviews = [
            item
            for item in contract.get("artifacts", [])
            if isinstance(item, dict) and item.get("kind") == "review"
        ]
        if len(reviews) != 1 or not isinstance(reviews[0].get("path"), str):
            return None
        path = task_dir / reviews[0]["path"]
        try:
            receipt = valid_review_receipt(
                task_dir,
                review_id=review_id,
                supersedes_review_id=supersedes_review_id,
            )
        except (KeyError, ReviewError):
            return None
        write_json(path, receipt)
        return path

    def error_codes(self, task_dir: Path, mode: str = "approval") -> set[str]:
        return {issue.code for issue in validate_task(task_dir, mode) if issue.level == "error"}

    def test_valid_bundle_passes_approval(self) -> None:
        self.assertEqual(set(), self.error_codes(self.make_task()))

    def test_compact_semantic_sections_pass_approval(self) -> None:
        plan = compact_plan()
        self.assertLessEqual(len(re.findall(r"^##\s+", plan, re.MULTILINE)), 14)
        self.assertEqual(set(), self.error_codes(self.make_task(plan=plan)))

    def test_profile_line_budget_is_warning_only(self) -> None:
        plan = valid_plan("\n".join(f"补充证据 {index}" for index in range(220)))
        issues = validate_task(self.make_task(plan=plan), "approval")
        budget_issues = [
            issue for issue in issues if issue.code == "TASK_PLAN_SOFT_BUDGET_EXCEEDED"
        ]
        self.assertEqual(1, len(budget_issues))
        self.assertEqual("warning", budget_issues[0].level)
        self.assertFalse(any(issue.level == "error" for issue in issues))

    def test_validation_timeout_is_optional_and_positive(self) -> None:
        contract = valid_contract()
        contract["validations"][0]["timeout_seconds"] = 45
        self.assertEqual(set(), self.error_codes(self.make_task(contract=contract)))

        contract = valid_contract()
        contract["validations"][0]["timeout_seconds"] = 0
        self.assertIn(
            "TASK_CONTRACT_INVALID_VALUE",
            self.error_codes(self.make_task(contract=contract)),
        )

    def test_full_profile_review_uses_strict_dispatch(self) -> None:
        contract = valid_contract()
        contract["plan_profile"] = "full"
        plan = (
            valid_plan()
            .replace("Plan profile: lite", "Plan profile: full")
            .replace(
                "Expected dispatch policy: `conditional`",
                "Expected dispatch policy: `strict`",
            )
        )
        task_dir = self.make_task(contract, plan)
        receipt_path = (
            task_dir / "artifacts" / "reviews" / "plan-review-attempt-1.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        dispatch_path = resolve_review_ref(
            receipt["reviewer"]["dispatch_ref"],
            task_dir / "artifacts" / "reviews",
        )
        dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
        self.assertEqual("strict", dispatch["policy"])

    def test_plan_review_context_must_be_approval_included(self) -> None:
        task_dir = self.make_task()
        extra = task_dir / "unapproved-note.md"
        extra.write_text("unapproved context\n", encoding="utf-8")
        path = task_dir / "artifacts" / "reviews" / "plan-review-attempt-1.json"
        receipt = valid_review_receipt(
            task_dir,
            extra_context_entries=[("unapproved-note.md", "other")],
        )
        write_json(path, receipt)
        self.assertIn(
            "TASK_ARTIFACT_REVIEW_CONTEXT_UNATTESTED",
            self.error_codes(task_dir),
        )

    def test_missing_plan_review_receipt_is_rejected(self) -> None:
        task_dir = self.make_task()
        (task_dir / "artifacts" / "reviews" / "plan-review-attempt-1.json").unlink()
        self.assertIn("TASK_ARTIFACT_REVIEW_MISSING", self.error_codes(task_dir))

    def test_draft_allows_missing_plan_review_receipt(self) -> None:
        task_dir = self.make_task()
        (task_dir / "artifacts" / "reviews" / "plan-review-attempt-1.json").unlink()
        self.assertNotIn(
            "TASK_ARTIFACT_REVIEW_MISSING",
            self.error_codes(task_dir, mode="draft"),
        )

    def test_draft_rejects_noncanonical_plan_review_path(self) -> None:
        contract = valid_contract()
        contract["artifacts"][0]["path"] = "artifacts/reviews/current.json"
        plan = valid_plan().replace(
            "artifacts/reviews/plan-review-attempt-1.json",
            "artifacts/reviews/current.json",
        )
        self.assertIn(
            "TASK_CONTRACT_REVIEW_PATH_INVALID",
            self.error_codes(self.make_task(contract, plan), mode="draft"),
        )

    def test_wrong_review_profile_is_rejected(self) -> None:
        task_dir = self.make_task()
        path = task_dir / "artifacts" / "reviews" / "plan-review-attempt-1.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["profile"] = "code-review"
        write_json(path, receipt)
        self.assertIn("TASK_ARTIFACT_REVIEW_INVALID", self.error_codes(task_dir))

    def test_wrong_review_scope_is_rejected(self) -> None:
        task_dir = self.make_task()
        path = task_dir / "artifacts" / "reviews" / "plan-review-attempt-1.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["scope"] = {"kind": "standalone"}
        write_json(path, receipt)
        self.assertIn("TASK_ARTIFACT_REVIEW_INVALID", self.error_codes(task_dir))

    def test_open_major_review_cannot_pass_approval(self) -> None:
        task_dir = self.make_task()
        path = task_dir / "artifacts" / "reviews" / "plan-review-attempt-1.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["findings"] = [
            {
                "id": "FIND-001",
                "category": "correctness",
                "origin": {"review_id": None, "finding_id": None},
                "severity": "major",
                "status": "open",
                "title": "验证无法证伪验收",
                "claim": "VAL-01 只检查退出码，未观察 AC-01 的结果。",
                "impact": "错误实现仍可能通过计划门禁。",
                "recommendation": "增加可观察结果断言。",
                "evidence": [
                    {
                        "path": "execution-plan.md",
                        "line": 1,
                        "symbol": None,
                        "artifact_ref": None,
                        "standard_ref": None,
                        "detail": "当前验证章节缺少结果断言。",
                        "claim_source": "read",
                    }
                ],
                "confidence": "high",
                "disposition_reason": None,
            }
        ]
        receipt["verdict"] = "changes_required"
        requirement_check = receipt["coverage"]["requirement_checks"][0]
        requirement_check.update(
            {
                "status": "violated",
                "finding_ids": ["FIND-001"],
                "summary": "当前验证不足以证明要求。",
            }
        )
        receipt["open_counts"] = {
            "blocking": 0,
            "major": 1,
            "minor": 0,
            "advisory": 0,
            "total": 1,
        }
        sync_semantic_result(receipt, task_dir)
        write_json(path, receipt)
        self.assertIn("TASK_ARTIFACT_REVIEW_NOT_PASSED", self.error_codes(task_dir))

    def test_stale_plan_review_receipt_is_rejected(self) -> None:
        task_dir = self.make_task()
        plan_path = task_dir / "execution-plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8") + "\nAdditional approved intent.\n",
            encoding="utf-8",
        )
        issues = validate_task(task_dir, "approval")
        invalid = [issue for issue in issues if issue.code == "TASK_ARTIFACT_REVIEW_INVALID"]
        self.assertTrue(invalid)
        self.assertIn("REVIEW_DISPATCH_STALE", invalid[0].message)

    def test_next_review_attempt_supersedes_immediate_predecessor(self) -> None:
        task_dir = self.make_task()
        contract_path = task_dir / "plan-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["artifacts"][0]["path"] = (
            "artifacts/reviews/plan-review-attempt-2.json"
        )
        write_json(contract_path, contract)
        plan_path = task_dir / "execution-plan.md"
        plan_path.write_text(
            plan_path.read_text(encoding="utf-8").replace(
                "plan-review-attempt-1.json",
                "plan-review-attempt-2.json",
            ),
            encoding="utf-8",
        )
        self.write_current_review(
            task_dir,
            review_id="REV-PLAN-002",
            supersedes_review_id="REV-PLAN-001",
        )
        self.assertEqual(set(), self.error_codes(task_dir))

    def test_unknown_field_is_rejected(self) -> None:
        contract = valid_contract()
        contract["unknown_field"] = "not allowed"
        self.assertIn("TASK_CONTRACT_UNKNOWN_FIELD", self.error_codes(self.make_task(contract)))

    def test_stage_cycle_and_broken_reference_are_rejected(self) -> None:
        contract = valid_contract()
        stage = contract["stages"][0]
        stage["depends_on"] = ["STG-01", "STG-99"]
        codes = self.error_codes(self.make_task(contract))
        self.assertIn("TASK_CONTRACT_STAGE_CYCLE", codes)
        self.assertIn("TASK_CONTRACT_BROKEN_REFERENCE", codes)

    def test_required_artifact_must_exist(self) -> None:
        contract = valid_contract()
        contract["artifacts"] = [
            {
                "id": "ART-01",
                "kind": "architecture",
                "path": "artifacts/architecture/change-map.md",
                "required": True,
                "approval_included": True,
            }
        ]
        plan = valid_plan().replace("## Artifact Index\n\ncomplete", "## Artifact Index\n\nART-01")
        self.assertIn("TASK_ARTIFACT_MISSING", self.error_codes(self.make_task(contract, plan)))

    def test_required_artifact_must_be_attested_and_nonempty(self) -> None:
        contract = valid_contract()
        contract["artifacts"] = [
            {
                "id": "ART-01",
                "kind": "architecture",
                "path": "artifacts/architecture/change-map.md",
                "required": True,
                "approval_included": False,
            }
        ]
        plan = valid_plan().replace("## Artifact Index\n\ncomplete", "## Artifact Index\n\nART-01")
        task_dir = self.make_task(contract, plan)
        artifact = task_dir / "artifacts" / "architecture" / "change-map.md"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("", encoding="utf-8")
        codes = self.error_codes(task_dir)
        self.assertIn("TASK_CONTRACT_ARTIFACT_NOT_ATTESTED", codes)
        self.assertIn("TASK_ARTIFACT_EMPTY", codes)

    def test_plan_contract_id_drift_is_rejected(self) -> None:
        plan = valid_plan().replace("REQ-01", "REQ-99")
        codes = self.error_codes(self.make_task(plan=plan))
        self.assertIn("TASK_PLAN_MISSING_ID", codes)
        self.assertIn("TASK_PLAN_EXTRA_ID", codes)

    def test_stage_contract_drift_is_rejected(self) -> None:
        plan = valid_plan().replace("VAL-01 src/ unrelated/", "VAL-01 unrelated/")
        self.assertIn("TASK_PLAN_STAGE_DRIFT", self.error_codes(self.make_task(plan=plan)))

    def test_duplicate_stage_heading_is_rejected(self) -> None:
        duplicate = "### STG-01：实现并验证\nREQ-01 AC-01 NFR-01 VAL-01 src/ unrelated/"
        plan = valid_plan().replace("## 环境", f"{duplicate}\n\n## 环境")
        self.assertIn("TASK_PLAN_STAGE_DUPLICATE", self.error_codes(self.make_task(plan=plan)))

    def test_summary_revision_drift_is_rejected(self) -> None:
        plan = valid_plan().replace("Plan revision: 1", "Plan revision: 2")
        self.assertIn("TASK_PLAN_CONTRACT_DRIFT", self.error_codes(self.make_task(plan=plan)))

    def test_mutable_execution_section_is_rejected(self) -> None:
        plan = valid_plan("## 实施进度\n\ncurrent stage")
        self.assertIn("TASK_PLAN_MUTABLE_SECTION", self.error_codes(self.make_task(plan=plan)))

    def test_code_angle_brackets_are_not_template_placeholders(self) -> None:
        plan = valid_plan().replace(
            "## 上下文\n\ncomplete",
            "## 上下文\n\nList<T> 与 <video> 是被规划对象。",
        )
        self.assertNotIn(
            "TASK_PLAN_PLACEHOLDER",
            self.error_codes(self.make_task(plan=plan)),
        )

    def test_known_template_placeholder_is_rejected(self) -> None:
        plan = valid_plan().replace(
            "## 上下文\n\ncomplete",
            "## 上下文\n\n仍有 <task-id> 未替换。",
        )
        self.assertIn(
            "TASK_PLAN_PLACEHOLDER",
            self.error_codes(self.make_task(plan=plan)),
        )

    def test_stage_traceability_covers_acceptance_nfr_and_required_validation(self) -> None:
        contract = valid_contract()
        stage = contract["stages"][0]
        stage["acceptance_ids"] = []
        stage["nonfunctional_ids"] = []
        stage["validation_ids"] = []
        codes = self.error_codes(self.make_task(contract))
        self.assertIn("TASK_CONTRACT_UNCOVERED_STAGE_TRACE", codes)
        self.assertIn("TASK_CONTRACT_UNASSIGNED_VALIDATION", codes)

    def test_explicit_approval_policy_cannot_be_weakened(self) -> None:
        contract = valid_contract()
        policy = contract["approval_policy"]
        policy["commit_requires_explicit_authorization"] = False
        self.assertIn(
            "TASK_CONTRACT_APPROVAL_POLICY_WEAK",
            self.error_codes(self.make_task(contract)),
        )

    def test_high_risk_stage_requires_full_profile(self) -> None:
        contract = valid_contract()
        contract["stages"][0]["risk"] = "high"
        self.assertIn(
            "TASK_CONTRACT_PROFILE_UNDERSCOPED",
            self.error_codes(self.make_task(contract)),
        )

    def test_online_research_does_not_read_outside_task_dir(self) -> None:
        contract = valid_contract()
        contract["research"] = {
            "mode": "online-required",
            "evidence_artifact_ids": ["ART-01"],
            "unresolved": [],
        }
        contract["artifacts"] = [
            {
                "id": "ART-01",
                "kind": "research",
                "path": "../outside-research.md",
                "required": False,
                "approval_included": False,
            }
        ]
        plan = valid_plan().replace(
            "## Artifact Index\n\ncomplete",
            "## Artifact Index\n\nART-01",
        )
        task_dir = self.make_task(contract, plan)
        outside = task_dir.parent / "outside-research.md"
        outside.write_text("Source: https://example.com\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)

        codes = self.error_codes(task_dir)
        self.assertIn("TASK_CONTRACT_UNSAFE_PATH", codes)
        self.assertIn("TASK_PLAN_RESEARCH_SOURCE_MISSING", codes)

    def test_draft_allows_pending_gate_and_open_decision(self) -> None:
        task_dir = self.make_task(
            plan=valid_plan().replace(
                RESEARCH_GATE_BODY,
                "- Research result: `pending`",
            )
        )
        (task_dir / "pending-decisions.md").write_text("状态: open\n", encoding="utf-8")
        self.assertNotIn("TASK_PLAN_GATE_PENDING", self.error_codes(task_dir, mode="draft"))
        self.assertNotIn("TASK_PLAN_OPEN_DECISION", self.error_codes(task_dir, mode="draft"))

    def test_empty_or_url_only_gate_is_rejected(self) -> None:
        empty = valid_plan().replace(
            RESEARCH_GATE_BODY,
            "- Research result: `not-applicable`",
        )
        self.assertIn("TASK_PLAN_GATE_EMPTY", self.error_codes(self.make_task(plan=empty)))
        url_only = valid_plan().replace(
            RESEARCH_GATE_BODY,
            "- Research result: `not-applicable`\n"
            "- https://example.com/one\n"
            "- https://example.com/two\n"
            "- https://example.com/three",
        )
        self.assertIn("TASK_PLAN_GATE_EMPTY", self.error_codes(self.make_task(plan=url_only)))

    def test_dependency_plan_mode_drift_is_rejected(self) -> None:
        plan = valid_plan().replace(
            "Selection mode: `none`",
            "Selection mode: `change`",
        )
        self.assertIn(
            "TASK_DEPENDENCY_PLAN_DRIFT",
            self.error_codes(self.make_task(plan=plan)),
        )


if __name__ == "__main__":
    unittest.main()
