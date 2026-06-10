# dev-skills

本仓库用于沉淀可复用的开发类 skills。

## Skills

### complex-coding-harness

位置：`skills/complex-coding-harness/`

用途：面向复杂、长周期、高风险、多阶段、多仓库或容易受上下文压缩影响的 coding 任务，提供轻量、可恢复、可审计的执行协议。

核心约束：

- 复杂任务先制定方案，再等待用户明确批准。
- `Readiness Gate` 只表示方案可提交审批，不表示可以自动实现。
- 用户批准前不得进入实现阶段。
- 实施阶段按阶段执行，每阶段完成 review、验证、必要修复、记录更新和授权提交。
- 用户可用自然语言维护各项目 `docs/development.md`，agent 负责整理 `.harness/environment.md`。
- managed 任务使用统一 harness 工作分支，例如 `harness/feature`、`harness/fix`，并在 `execution-plan.md` 记录 `Git Context`。
- managed 任务最终交付必须携带任务结论、验证结果、未覆盖范围、commit 信息和关键证据；前端或可视化任务应提供截图或替代证据。

## Repository Layout

```text
skill.sh
skills/
└── complex-coding-harness/
    ├── SKILL.md
    ├── references/
    │   └── workflow.md
    └── templates/
        ├── environment.md
        ├── execution-plan.md
        └── pending-decisions.md
examples/
└── complex-coding-harness/
evals/
└── complex-coding-harness/
```

## Install

```sh
./skill.sh install "$HOME/.codex/skills"
```

On Windows PowerShell with Git Bash, WSL, or another POSIX-compatible shell available:

```powershell
sh .\skill.sh install "$env:USERPROFILE\.codex\skills"
```

## Notes

- 本仓库源码使用普通 `skills/` 目录，不把主结构放进 `.agents/skills/`。
- `skill.sh` 目前只提供基础复制安装，后续可按 Codex/Claude Code 约定继续增强。
- `.harness/tasks/` 是运行时任务记录，不是 skill 安装产物。
