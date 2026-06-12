---
name: process-manager
description: Manage local Windows long-running background processes through a persistent Python manager and bundled pm_* scripts. Use when Codex needs to start, stop, inspect, tail logs, wait for readiness, restart, or diagnose local dev servers, workers, watchers, model services, or other non-finite processes without blocking the main agent shell.
---

# Process Manager

Use this skill for local long-running background processes on Windows. Do not use it for finite commands such as tests, builds, lint, formatters, migrations, or one-off scripts that should return normally.

## Required Workflow

1. Read `references/workflow.md` before changing service configs or managing a process.
2. Run `scripts/pm_health.py` first. If the manager is offline, ask the user to start it or approve running `scripts/start_manager.ps1`.
3. Validate service config with `scripts/pm_validate.py` before `pm_start.py`.
4. Use only bundled `pm_*` scripts for lifecycle work. Do not call the manager API directly.
5. Stop services with `scripts/pm_stop.py` or `scripts/pm_restart.py`; do not kill arbitrary PIDs.
6. Use `scripts/pm_list.py --history` only when historical records are needed. The default list view is current state only.

## Hard Rules

- Support Windows only in this version.
- Require absolute paths for `cwd`, executable paths, script paths, and path-like file or directory arguments.
- Manage only long-running background processes.
- Keep process windows hidden; stdout and stderr go to manager-created log files.
- Do not use free-form shell commands, `shell: true`, `cmd-command`, `powershell-command`, or `powershell -Command`.
- Use `direct`, `cmd-file`, or `powershell-file` launchers only.
- Do not put generic top-level `host` or `port` fields in service config. Use readiness or startup arguments for endpoints.
- Keep all `running` and `stop_timeout` records. Inactive history is capped by manager config and pruned with its exact runDir only.

## Scripts

- `scripts/pm_init.py`: create `.harness/process-manager/` runtime config.
- `scripts/pm_health.py`: check manager availability.
- `scripts/pm_validate.py`: validate manager and service configs.
- `scripts/pm_start.py`: start a configured service.
- `scripts/pm_ready.py`: wait for readiness.
- `scripts/pm_status.py`: inspect one service or process key.
- `scripts/pm_logs.py`: show stdout/stderr log paths or tails.
- `scripts/pm_list.py`: list active/running processes; use `--history` for retained history.
- `scripts/pm_prune.py`: dry-run or apply inactive history pruning.
- `scripts/pm_stop.py`: stop a managed process.
- `scripts/pm_restart.py`: restart a service through stop/start.
- `scripts/pm_doctor.py`: diagnose local config, manager state, and common failures.

## Templates

Start from `templates/manager-config.json` and one of:

- `templates/service-direct.json`
- `templates/service-cmd-file.json`
- `templates/service-powershell-file.json`

Copy templates into the target workspace under `.harness/process-manager/` or a project-owned config location, then replace placeholder absolute paths.
