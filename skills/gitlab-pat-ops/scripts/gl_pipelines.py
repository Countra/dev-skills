#!/usr/bin/env python3
"""GitLab pipeline 与 job 只读命令。"""

from __future__ import annotations

import argparse
from typing import Iterable

from gitlab_ops import (
    add_common_args,
    add_pagination_args,
    make_client,
    output_client_result,
    project_path,
    quote_id,
    request_list,
    resource_path,
    run_cli,
    validate_iso8601,
)


JOB_SCOPES = (
    "created",
    "pending",
    "running",
    "failed",
    "success",
    "canceled",
    "skipped",
    "manual",
    "waiting_for_resource",
    "preparing",
)


def _add_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)


def _add_pipeline(parser: argparse.ArgumentParser) -> None:
    _add_project(parser)
    parser.add_argument("--pipeline-id", required=True)


def _add_job_scopes(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", action="append", choices=JOB_SCOPES, help="可重复传入多个 job scope")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="查询 GitLab pipeline 与 job")
    add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="列出项目 pipeline")
    add_common_args(list_parser)
    add_pagination_args(list_parser)
    _add_project(list_parser)
    list_parser.add_argument("--status")
    list_parser.add_argument("--ref")
    list_parser.add_argument("--sha")
    list_parser.add_argument("--source")
    list_parser.add_argument("--username")
    list_parser.add_argument("--name")
    list_parser.add_argument("--updated-after")
    list_parser.add_argument("--updated-before")
    list_parser.add_argument("--order-by", choices=["id", "status", "ref", "updated_at", "user_id"])
    list_parser.add_argument("--sort", choices=["asc", "desc"])

    get_parser = subparsers.add_parser("get", help="读取 pipeline 详情")
    add_common_args(get_parser)
    _add_pipeline(get_parser)

    latest_parser = subparsers.add_parser("latest", help="读取指定 ref 的最新 pipeline")
    add_common_args(latest_parser)
    _add_project(latest_parser)
    latest_parser.add_argument("--ref")

    for name, help_text in (("jobs", "列出 pipeline jobs"), ("bridges", "列出 pipeline bridges")):
        item = subparsers.add_parser(name, help=help_text)
        add_common_args(item)
        add_pagination_args(item)
        _add_pipeline(item)
        if name == "jobs":
            _add_job_scopes(item)
            item.add_argument("--include-retried", action="store_true")

    project_jobs = subparsers.add_parser("project-jobs", help="列出项目 jobs")
    add_common_args(project_jobs)
    add_pagination_args(project_jobs)
    _add_project(project_jobs)
    _add_job_scopes(project_jobs)
    project_jobs.add_argument("--include-retried", action="store_true")

    job_parser = subparsers.add_parser("job", help="读取 job 详情")
    add_common_args(job_parser)
    _add_project(job_parser)
    job_parser.add_argument("--job-id", required=True)

    mr_parser = subparsers.add_parser("mr", help="列出 MR pipelines")
    add_common_args(mr_parser)
    add_pagination_args(mr_parser)
    _add_project(mr_parser)
    mr_parser.add_argument("--iid", required=True)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    client = make_client(args)
    project = project_path(args.project)
    if args.command == "list":
        params = {
            "status": args.status,
            "ref": args.ref,
            "sha": args.sha,
            "source": args.source,
            "username": args.username,
            "name": args.name,
            "updated_after": validate_iso8601(args.updated_after, "--updated-after"),
            "updated_before": validate_iso8601(args.updated_before, "--updated-before"),
            "order_by": args.order_by,
            "sort": args.sort,
        }
        value = request_list(client, f"{project}/pipelines", args, params=params)
        output_client_result(client, value, pretty=args.pretty, operation="pipelines.list")
        return 0
    if args.command == "get":
        value = client.request("GET", f"{project}/pipelines/{quote_id(args.pipeline_id)}")
        output_client_result(client, value, pretty=args.pretty, operation="pipelines.get")
        return 0
    if args.command == "latest":
        value = client.request("GET", f"{project}/pipelines/latest", params={"ref": args.ref})
        output_client_result(client, value, pretty=args.pretty, operation="pipelines.latest")
        return 0
    if args.command in {"jobs", "bridges"}:
        path = f"{project}/pipelines/{quote_id(args.pipeline_id)}/{args.command}"
        params = None
        if args.command == "jobs":
            params = {"scope[]": args.scope, "include_retried": args.include_retried or None}
        value = request_list(client, path, args, params=params)
        output_client_result(client, value, pretty=args.pretty, operation=f"pipelines.{args.command}")
        return 0
    if args.command == "project-jobs":
        params = {"scope[]": args.scope, "include_retried": args.include_retried or None}
        value = request_list(client, f"{project}/jobs", args, params=params)
        output_client_result(client, value, pretty=args.pretty, operation="jobs.list")
        return 0
    if args.command == "job":
        value = client.request("GET", f"{project}/jobs/{quote_id(args.job_id)}")
        output_client_result(client, value, pretty=args.pretty, operation="jobs.get")
        return 0
    if args.command == "mr":
        value = request_list(client, f"{resource_path('mr', args.project, args.iid)}/pipelines", args)
        output_client_result(client, value, pretty=args.pretty, operation="merge_request_pipelines.list")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
