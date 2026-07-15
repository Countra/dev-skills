"""可解释 hybrid retrieval、硬兼容过滤与状态安全组合。"""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

from .canonical_store import CanonicalStore
from .compatibility import RuntimeContext, compatibility_reasons, optional_text
from .errors import VerifierError
from .knowledge_index import KnowledgeIndex
from .sensitivity import bind_parameters, normalize_parameter_schema, placeholders
from .text_normalization import all_ngrams, latin_tokens, normalize_text


RRF_K = 60
DEFAULT_MIN_SCORE = 0.62
DEFAULT_MIN_MARGIN = 0.05
RetrievalContext = RuntimeContext
_optional_text = optional_text


def _set_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    union = len(left | right)
    return max(intersection / union, intersection / min(len(left), len(right)))


def _lexical_similarity(query: str, values: list[str]) -> float:
    normalized = normalize_text(query)
    query_tokens = latin_tokens(normalized)
    query_grams = all_ngrams([normalized])
    best = 0.0
    for value in values:
        candidate = normalize_text(value)
        if not candidate:
            continue
        if normalized == candidate:
            return 1.0
        token_score = _set_similarity(query_tokens, latin_tokens(candidate))
        gram_score = _set_similarity(query_grams, all_ngrams([candidate]))
        sequence_score = SequenceMatcher(None, normalized, candidate, autojunk=False).ratio()
        containment = min(len(normalized), len(candidate)) / max(len(normalized), len(candidate)) if normalized in candidate or candidate in normalized else 0.0
        best = max(best, 0.35 * token_score + 0.35 * gram_score + 0.20 * sequence_score + 0.10 * containment)
    return min(best, 1.0)


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(str(row["payload_json"]))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise VerifierError("knowledge_index_invalid", "derived payload JSON 无效", status=500) from exc
    if not isinstance(value, dict):
        raise VerifierError("knowledge_index_invalid", "derived payload 必须是 object", status=500)
    return value


def _aliases(row: dict[str, Any]) -> list[str]:
    try:
        value = json.loads(str(row["aliases_json"]))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise VerifierError("knowledge_index_invalid", "derived aliases JSON 无效", status=500) from exc
    return [str(item) for item in value] if isinstance(value, list) else []


class HybridRetriever:
    """融合 exact、alias、FTS 与 ngram；不使用 recent filler。"""

    def __init__(self, store: CanonicalStore) -> None:
        self.store = store
        self.index = KnowledgeIndex(store.paths["index"])

    def close(self) -> None:
        self.index.close()

    def __enter__(self) -> "HybridRetriever":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001
        self.close()

    def _compatibility_reasons(self, row: dict[str, Any], context: RetrievalContext) -> list[str]:
        return compatibility_reasons(
            {
                "appVersionMin": row.get("app_version_min"),
                "appVersionMax": row.get("app_version_max"),
                "screenDigest": row.get("screen_digest"),
                "preState": row.get("pre_state"),
                "risk": row.get("risk_level"),
            },
            context,
        )

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        asset = self.store.get_asset(asset_id)
        compatibility = asset.payload["compatibility"]
        result = {
            "assetId": asset.asset_id,
            "kind": asset.kind,
            "appId": asset.app_id,
            "goal": asset.goal,
            "aliases": list(asset.aliases),
            "requiredParams": asset.payload["requiredParameters"],
            "parameterSchema": asset.payload["parameterSchema"],
            "compatibility": compatibility,
            "createdAt": asset.created_at,
        }
        if asset.kind == "workflow":
            result["actionIds"] = asset.payload["actionIds"]
        return {"ok": True, "asset": result}

    def list_assets(self, app_id: str | None, kind: str | None, limit: int = 50) -> dict[str, Any]:
        if kind not in {None, "action", "workflow"}:
            raise VerifierError("invalid_asset_kind", f"asset kind 不受支持：{kind}")
        if not 1 <= int(limit) <= 200:
            raise VerifierError("invalid_asset_limit", "asset list limit 必须在 1..200")
        rows = self.index.list(_optional_text(app_id), kind, limit)
        assets = [
            {
                "assetId": row["asset_id"],
                "kind": row["kind"],
                "appId": row["app_id"],
                "goal": row["goal"],
                "aliases": _aliases(row),
                "risk": row.get("risk_level") or "low",
                "preState": row.get("pre_state"),
                "postState": row.get("post_state"),
                "successCount": int(row.get("success_count") or 0),
                "failureCount": int(row.get("failure_count") or 0),
                "lastVerifiedAt": row.get("last_verified_at"),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
        return {"ok": True, "count": len(assets), "assets": assets}

    def stats(self) -> dict[str, Any]:
        return {"ok": True, **self.index.stats()}

    def record_outcome(self, asset_id: str, succeeded: bool, verified_at: str) -> dict[str, Any]:
        return self.index.record_outcome(asset_id, succeeded, verified_at)

    def search(
        self,
        query: str,
        context_value: Any,
        *,
        kind: str | None = None,
        limit: int = 3,
        min_score: float = DEFAULT_MIN_SCORE,
        min_margin: float = DEFAULT_MIN_MARGIN,
        explain: bool = False,
    ) -> dict[str, Any]:
        context = RetrievalContext.decode(context_value)
        goal = query.strip()
        if not goal:
            raise VerifierError("knowledge_query_required", "knowledge query 不能为空")
        if len(goal) > 500:
            raise VerifierError("knowledge_query_too_long", "knowledge query 超过 500 字符上限")
        if kind not in {None, "action", "workflow"}:
            raise VerifierError("invalid_asset_kind", f"asset kind 不受支持：{kind}")
        if not 1 <= int(limit) <= 10:
            raise VerifierError("invalid_retrieval_limit", "retrieval limit 必须在 1..10")
        if not 0.0 <= float(min_score) <= 1.0 or not 0.0 <= float(min_margin) <= 1.0:
            raise VerifierError("invalid_retrieval_threshold", "retrieval threshold 必须在 0..1")
        normalized = normalize_text(goal)
        channels: dict[str, list[str]] = {}
        exact = self.index.exact(context.app_id, normalized)
        channels["exactGoal"] = exact["goal"]
        channels["exactAlias"] = exact["alias"]
        channels["fts"] = self.index.fts(context.app_id, goal)
        ngram_rows = self.index.ngram(context.app_id, all_ngrams([goal]))
        channels["ngram"] = [asset_id for asset_id, _ in ngram_rows]
        candidate_ids = {asset_id for values in channels.values() for asset_id in values}
        rows = self.index.rows(candidate_ids)
        channel_weights = {"exactGoal": 1.0, "exactAlias": 0.95, "fts": 0.75, "ngram": 0.65}
        ranks = {
            name: {asset_id: rank for rank, asset_id in enumerate(values, start=1)}
            for name, values in channels.items()
        }
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for asset_id in sorted(candidate_ids):
            row = rows.get(asset_id)
            if row is None:
                continue
            reasons = self._compatibility_reasons(row, context)
            if kind and row.get("kind") != kind:
                reasons.append("kind_mismatch")
            matched = {name: rank_map[asset_id] for name, rank_map in ranks.items() if asset_id in rank_map}
            if reasons:
                rejected.append({"assetId": asset_id, "reasons": reasons, "channels": matched})
                continue
            aliases = _aliases(row)
            lexical = _lexical_similarity(goal, [str(row["goal"]), *aliases])
            rrf_raw = sum(channel_weights[name] / (RRF_K + rank) for name, rank in matched.items())
            rrf_max = sum(channel_weights[name] / (RRF_K + 1) for name in matched) or 1.0
            rrf = min(rrf_raw / rrf_max, 1.0)
            exact_score = 1.0 if "exactGoal" in matched else 0.98 if "exactAlias" in matched else 0.0
            successes = max(0, int(row.get("success_count") or 0))
            failures = max(0, int(row.get("failure_count") or 0))
            reliability = (successes + 1) / (successes + failures + 2)
            score = exact_score or min(1.0, 0.74 * lexical + 0.26 * rrf)
            payload = _row_payload(row)
            parameter_schema = normalize_parameter_schema(payload.get("parameterSchema"))
            required_params = list(payload.get("requiredParameters") or [])
            candidate: dict[str, Any] = {
                "assetId": asset_id,
                "kind": row["kind"],
                "appId": row["app_id"],
                "goal": row["goal"],
                "score": round(score, 6),
                "risk": row.get("risk_level") or "low",
                "preState": row.get("pre_state"),
                "postState": row.get("post_state"),
                "requiredParams": required_params,
                "executable": not (set(required_params) - set(parameter_schema)),
                "_reliability": reliability,
            }
            if explain:
                candidate["explain"] = {
                    "channels": matched,
                    "lexical": round(lexical, 6),
                    "rrf": round(rrf, 6),
                    "reliability": round(reliability, 6),
                }
            accepted.append(candidate)
        accepted.sort(
            key=lambda item: (
                -float(item["score"]),
                -float(item["_reliability"]),
                str(item["assetId"]),
            )
        )
        selected = accepted[: int(limit)]
        top = float(selected[0]["score"]) if selected else 0.0
        second = float(selected[1]["score"]) if len(selected) > 1 else 0.0
        reason = None
        if not selected:
            reason = "no_compatible_candidate" if rejected else "no_lexical_candidate"
        elif top < min_score:
            reason = "score_below_threshold"
        elif len(selected) > 1 and top - second < min_margin:
            reason = "ambiguous_margin"
        result: dict[str, Any] = {
            "ok": True,
            "decision": "abstain" if reason else "reuse",
            "query": {"appId": context.app_id, "goal": goal},
            "candidates": selected,
            "thresholds": {"minScore": min_score, "minMargin": min_margin},
        }
        if reason:
            result["abstain"] = {"reason": reason, "topScore": round(top, 6), "margin": round(top - second, 6)}
        for candidate in selected:
            candidate.pop("_reliability", None)
        if explain:
            result["explain"] = {
                "channelCandidateCounts": {name: len(values) for name, values in channels.items()},
                "rejected": rejected[:50],
            }
        return result

    def compose(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise VerifierError("invalid_composition", "composition payload 必须是 object")
        context = RetrievalContext.decode(payload)
        if context.pre_state is None:
            raise VerifierError("composition_pre_state_required", "composition 需要当前 preState", status=409)
        subgoals = payload.get("subgoals")
        if not isinstance(subgoals, list) or not subgoals or len(subgoals) > 20:
            raise VerifierError("invalid_composition", "subgoals 必须包含 1..20 个目标")
        bindings = payload.get("bindings") if isinstance(payload.get("bindings"), dict) else {}
        selected = []
        previous_state = context.pre_state
        merged_schema: dict[str, dict[str, Any]] = {}
        templates: list[dict[str, Any]] = []
        for position, raw_goal in enumerate(subgoals):
            goal = str(raw_goal).strip()
            local_context = dict(payload)
            local_context["preState"] = previous_state
            result = self.search(goal, local_context, kind="action", limit=3, explain=True)
            if result["decision"] != "reuse":
                raise VerifierError(
                    "composition_candidate_missing",
                    f"子目标无法安全复用：{goal}",
                    status=409,
                    details={"position": position, "retrieval": result},
                )
            candidate = result["candidates"][0]
            if not candidate.get("preState") or not candidate.get("postState"):
                raise VerifierError("state_contract_required", f"action asset 缺少状态边：{candidate['assetId']}", status=409)
            if previous_state is not None and candidate["preState"] != previous_state:
                raise VerifierError("state_transition_mismatch", f"action asset 状态无法衔接：{candidate['assetId']}", status=409)
            asset = self.store.get_asset(str(candidate["assetId"]))
            action = asset.payload.get("action")
            if not isinstance(action, dict):
                raise VerifierError("asset_not_executable", f"action asset 缺少 payload.action：{asset.asset_id}", status=409)
            schema = normalize_parameter_schema(asset.payload.get("parameterSchema"))
            for name, definition in schema.items():
                if name in merged_schema and merged_schema[name] != definition:
                    raise VerifierError("parameter_schema_conflict", f"组合参数 schema 冲突：{name}", status=409)
                merged_schema[name] = definition
            local_bindings = {name: bindings[name] for name in schema if name in bindings}
            bind_parameters(action, local_bindings, schema)
            templates.append(action)
            selected.append(candidate["assetId"])
            previous_state = str(candidate["postState"])
        undeclared = sorted(set(bindings) - set(merged_schema))
        if undeclared:
            raise VerifierError("undeclared_parameter", f"bindings 包含未声明参数：{undeclared}")
        return {
            "ok": True,
            "decision": "compose",
            "assetIds": selected,
            "requiredParams": sorted(placeholders(templates)),
            "parameterSchema": merged_schema,
            "postState": previous_state,
        }
