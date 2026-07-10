"""issue/MR metadata 更新参数与显式清空语义。"""

from __future__ import annotations

import argparse
from typing import Any

from .errors import GitLabSkillError
from .text_input import parse_csv, parse_int_csv, read_optional_text_from_args, validate_yyyy_mm_dd


def add_description_update_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--description")
    group.add_argument("--description-file")
    group.add_argument("--stdin", dest="description_stdin", action="store_true")
    group.add_argument("--clear-description", action="store_true")


def description_update(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if args.clear_description:
        return {"description": ""}, "clear-description"
    description, source = read_optional_text_from_args(
        args,
        "description",
        "description_file",
        "description_stdin",
        "description",
    )
    if description is None:
        return {}, "none"
    if description == "":
        raise GitLabSkillError("空描述必须使用 --clear-description 明确表达")
    return {"description": description}, source


def add_label_update_args(parser: argparse.ArgumentParser) -> None:
    full = parser.add_mutually_exclusive_group()
    full.add_argument("--labels", help="用逗号分隔的完整 label 集合替换现值")
    full.add_argument("--clear-labels", action="store_true")
    parser.add_argument("--add-labels", help="追加逗号分隔的 labels")
    parser.add_argument("--remove-labels", help="移除逗号分隔的 labels")


def label_update(args: argparse.Namespace) -> dict[str, Any]:
    labels = parse_csv(args.labels)
    additions = parse_csv(args.add_labels)
    removals = parse_csv(args.remove_labels)
    for raw_value, parsed, option in (
        (args.labels, labels, "--labels"),
        (args.add_labels, additions, "--add-labels"),
        (args.remove_labels, removals, "--remove-labels"),
    ):
        if raw_value is not None and not parsed:
            raise GitLabSkillError(f"{option} 不能为空；清空 labels 请使用 --clear-labels")
    if (labels is not None or args.clear_labels) and (additions is not None or removals is not None):
        raise GitLabSkillError("--labels/--clear-labels 不能与 --add-labels/--remove-labels 同时使用")
    overlap = set(additions or ()) & set(removals or ())
    if overlap:
        raise GitLabSkillError("同一 label 不能在一次更新中同时添加和移除")
    body: dict[str, Any] = {}
    if labels is not None:
        body["labels"] = ",".join(labels)
    elif args.clear_labels:
        body["labels"] = ""
    if additions is not None:
        body["add_labels"] = ",".join(additions)
    if removals is not None:
        body["remove_labels"] = ",".join(removals)
    return body


def add_milestone_update_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--milestone-id", type=int)
    group.add_argument("--remove-milestone", action="store_true")


def milestone_update(args: argparse.Namespace) -> dict[str, Any]:
    if args.remove_milestone:
        return {"milestone_id": 0}
    if args.milestone_id is not None:
        if args.milestone_id <= 0:
            raise GitLabSkillError("--milestone-id 必须大于 0；移除 milestone 请使用 --remove-milestone")
        return {"milestone_id": args.milestone_id}
    return {}


def add_id_list_update_args(
    parser: argparse.ArgumentParser,
    *,
    option: str,
    unassign_option: str,
    help_noun: str,
) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(option, help=f"逗号分隔 {help_noun} id")
    group.add_argument(unassign_option, action="store_true", help=f"清空全部 {help_noun}")


def id_list_update(
    args: argparse.Namespace,
    *,
    value_attr: str,
    unassign_attr: str,
    body_key: str,
    label: str,
) -> dict[str, Any]:
    if getattr(args, unassign_attr):
        return {body_key: []}
    raw_value = getattr(args, value_attr)
    value = parse_int_csv(raw_value, label)
    if raw_value is not None and not value:
        raise GitLabSkillError(f"{label} 不能为空；清空请使用对应的 unassign 参数")
    return {body_key: value} if value is not None else {}


def add_due_date_update_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--due-date")
    group.add_argument("--remove-due-date", action="store_true")


def due_date_update(args: argparse.Namespace) -> dict[str, Any]:
    if args.remove_due_date:
        return {"due_date": ""}
    value = validate_yyyy_mm_dd(args.due_date, "--due-date")
    return {"due_date": value} if value is not None else {}
