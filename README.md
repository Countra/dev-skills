# dev-skills

本仓库用于沉淀可复用的开发类 skills。

## Skills

### complex-coding-harness

位置：`skills/complex-coding-harness/`

用途：面向复杂、长周期、高风险、多阶段、多仓库或容易受上下文压缩影响的 coding 任务，提供轻量、可恢复、可审计的执行协议。

核心约束：

- 复杂任务先制定方案，再等待用户明确批准。
- 方案制定阶段使用 `Plan Quality Gate` 检查影响面、证据等级和方案变更触发条件。
- `Readiness Gate` 只表示方案可提交审批，不表示可以自动实现。
- 用户批准前不得进入实现阶段。
- 实施阶段按 `Stage Contract`、`Stage Entry Gate` 和 `Stage Exit Gate` 执行，每阶段完成 review、验证、必要修复、记录更新和授权提交。
- 用户可用自然语言维护各项目 `docs/development.md`，agent 负责整理 `.harness/environment.md`。
- managed 任务使用统一 harness 工作分支，例如 `harness/feature`、`harness/fix`，并在 `execution-plan.md` 记录 `Git Context`。
- skill 文件更新后，用户可在会话中提示 agent 重新读取最新规则；不引入 tag 或自动迁移，旧任务状态只在自然更新时按新规则补齐。
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

默认安装会在目标目录已存在 `complex-coding-harness` 时停止，避免混合旧文件：

```sh
./skill.sh install "$HOME/.codex/skills"
```

如需明确替换已有安装，使用 `--force`。该模式只会替换目标 skills 目录下的 `complex-coding-harness`：

```sh
./skill.sh install --force "$HOME/.codex/skills"
```

On Windows PowerShell with Git Bash, WSL, or another POSIX-compatible shell available:

```powershell
sh .\skill.sh install "$env:USERPROFILE\.codex\skills"
```

如果 `sh` 不在 PowerShell 的 `PATH` 中，请在 Git Bash、MSYS2 或 WSL 终端进入仓库后执行同样的 `./skill.sh install ...` 命令，或使用对应 shell 的完整路径启动。

## Notes

- 本仓库源码使用普通 `skills/` 目录，不把主结构放进 `.agents/skills/`。
- `skill.sh` 只安装 skill 源文件，不写入运行时任务状态。
- `.harness/tasks/` 是运行时任务记录，不是 skill 安装产物。
