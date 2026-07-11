from __future__ import annotations

import argparse
import importlib
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import gl_approvals  # noqa: E402
import gl_commits  # noqa: E402
import gl_discussions  # noqa: E402
import gl_mr_diffs  # noqa: E402
import gl_namespaces  # noqa: E402
import gl_pipelines  # noqa: E402
import gl_resource_events  # noqa: E402
import gl_templates  # noqa: E402
from fakes import FakeClient, run_and_parse  # noqa: E402
from gitlab_ops.registry import CAPABILITIES, PROHIBITED  # noqa: E402


def parser_subcommands(module) -> set[str]:  # noqa: ANN001
    parser = module.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


class ResourceTests(unittest.TestCase):
    def test_new_read_resources_route_to_documented_endpoints(self) -> None:
        cases = (
            (gl_namespaces, ["list", "--search", "group"], "/namespaces"),
            (gl_namespaces, ["get", "--namespace", "group/sub"], "/namespaces/group%2Fsub"),
            (gl_commits, ["list", "--project", "group/proj", "--ref-name", "main"], "/repository/commits"),
            (gl_commits, ["get", "--project", "group/proj", "--sha", "abc"], "/commits/abc"),
            (gl_commits, ["refs", "--project", "group/proj", "--sha", "abc"], "/commits/abc/refs"),
            (gl_commits, ["merge-requests", "--project", "group/proj", "--sha", "abc"], "/commits/abc/merge_requests"),
            (gl_commits, ["diff", "--project", "group/proj", "--sha", "abc"], "/commits/abc/diff"),
            (gl_templates, ["list", "--project", "group/proj", "--type", "issues"], "/templates/issues"),
            (gl_templates, ["get", "--project", "group/proj", "--type", "merge_requests", "--name", "feature"], "/templates/merge_requests/feature"),
            (gl_mr_diffs, ["list", "--project", "group/proj", "--iid", "4"], "/merge_requests/4/diffs"),
            (gl_mr_diffs, ["versions", "--project", "group/proj", "--iid", "4"], "/merge_requests/4/versions"),
            (gl_mr_diffs, ["get-version", "--project", "group/proj", "--iid", "4", "--version-id", "7"], "/versions/7"),
            (gl_pipelines, ["list", "--project", "group/proj"], "/projects/group%2Fproj/pipelines"),
            (gl_pipelines, ["get", "--project", "group/proj", "--pipeline-id", "9"], "/pipelines/9"),
            (gl_pipelines, ["latest", "--project", "group/proj", "--ref", "main"], "/pipelines/latest"),
            (gl_pipelines, ["jobs", "--project", "group/proj", "--pipeline-id", "9"], "/pipelines/9/jobs"),
            (gl_pipelines, ["bridges", "--project", "group/proj", "--pipeline-id", "9"], "/pipelines/9/bridges"),
            (gl_pipelines, ["project-jobs", "--project", "group/proj"], "/projects/group%2Fproj/jobs"),
            (gl_pipelines, ["job", "--project", "group/proj", "--job-id", "10"], "/jobs/10"),
            (gl_pipelines, ["mr", "--project", "group/proj", "--iid", "4"], "/merge_requests/4/pipelines"),
            (gl_approvals, ["summary", "--project", "group/proj", "--iid", "4"], "/merge_requests/4/approvals"),
            (gl_approvals, ["state", "--project", "group/proj", "--iid", "4"], "/merge_requests/4/approval_state"),
            (gl_approvals, ["rules", "--project", "group/proj", "--iid", "4"], "/merge_requests/4/approval_rules"),
            (gl_discussions, ["list", "--resource", "issue", "--project", "group/proj", "--iid", "3"], "/issues/3/discussions"),
            (gl_discussions, ["get", "--resource", "mr", "--project", "group/proj", "--iid", "4", "--discussion-id", "abc"], "/merge_requests/4/discussions/abc"),
        )
        for module, argv, suffix in cases:
            with self.subTest(module=module.__name__, command=argv[0]):
                client = FakeClient()
                code, value = run_and_parse(module, argv, client)
                self.assertEqual(code, 0)
                self.assertTrue(value["ok"])
                self.assertTrue(any(suffix in call[1] for call in client.request_calls))

    def test_all_resource_event_combinations_are_composable(self) -> None:
        segment = {"state": "resource_state_events", "label": "resource_label_events", "milestone": "resource_milestone_events"}
        plural = {"issue": "issues", "mr": "merge_requests"}
        for resource in ("issue", "mr"):
            for event in segment:
                for command in ("list", "get"):
                    with self.subTest(resource=resource, event=event, command=command):
                        argv = [
                            command,
                            "--resource",
                            resource,
                            "--event",
                            event,
                            "--project",
                            "group/proj",
                            "--iid",
                            "4",
                        ]
                        if command == "get":
                            argv.extend(["--event-id", "8"])
                        client = FakeClient()
                        run_and_parse(gl_resource_events, argv, client)
                        suffix = f"/{plural[resource]}/4/{segment[event]}" + ("/8" if command == "get" else "")
                        self.assertTrue(any(suffix in call[1] for call in client.request_calls))

    def test_registry_is_unique_complete_and_parser_aligned(self) -> None:
        ids = [item.capability_id for item in CAPABILITIES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(set(ids) & {item["capability_id"] for item in PROHIBITED})
        self.assertFalse(any("/changes" in item.endpoint for item in CAPABILITIES))
        self.assertFalse(any(item.subcommand == "update-description" for item in CAPABILITIES))
        for item in CAPABILITIES:
            with self.subTest(capability=item.capability_id):
                script = SCRIPT_DIR / item.script
                self.assertTrue(script.is_file())
                if item.subcommand:
                    module = importlib.import_module(script.stem)
                    self.assertIn(item.subcommand, parser_subcommands(module))
                if item.mode == "write":
                    self.assertIn(item.method, {"POST", "PUT"})
                    self.assertIn("exact preview fingerprint", item.confirmation)


if __name__ == "__main__":
    unittest.main()
