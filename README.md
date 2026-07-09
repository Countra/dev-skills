# dev-skills

本仓库用于沉淀可复用的开发类 skills。

## Skills

### complex-coding-planner

位置：`skills/complex-coding-planner/`

用途：为复杂、长周期、高风险、多阶段、多仓库或容易受上下文压缩影响的 coding 任务制定可恢复、可审计的实施方案。

核心约束：

- 复杂任务先制定方案，再等待用户明确批准。
- 方案制定阶段使用 `Plan Quality Gate` 检查影响面、证据等级和方案变更触发条件。
- `Research Gate` 必须判断不确定项是否为 `none`、`local-only`、`online-required` 或 `blocked-by-access`；涉及可能变化的外部事实时优先查询官方或一手资料。
- `Standards Discovery Gate` 必须识别语言、技术栈、框架、API 类型和架构风险，收集官方/一手或高质量规范来源并形成 standards index。
- `Development Quality Gate` 必须覆盖代码标准、静态质量、架构边界、设计模式取舍、低耦合高内聚和验证映射。
- `Plan Self-Review` 必须主动复查缺陷、优化点、缺失项、风险和一致性；发现问题先修复计划。
- `Readiness Gate` 只表示方案可提交审批，不表示可以自动实现。
- 用户批准前不得进入实现阶段。
- 用户可用自然语言维护各项目 `docs/development.md`，agent 负责整理 `.harness/environment.md`。
- managed 任务使用统一 harness 工作分支，例如 `harness/feature`、`harness/fix`，并在 `execution-plan.md` 记录 `Git Context`。
- `Readiness Gate` 通过后必须停止，等待用户批准；实施阶段交给 `complex-coding-executor`。

### complex-coding-executor

位置：`skills/complex-coding-executor/`

用途：执行已经由 `complex-coding-planner` 制定并获用户批准的 managed 任务计划。

核心约束：

- 每轮开始读取 `.harness/active-task.json`、`.harness/environment.md` 和当前任务 `execution-plan.md`。
- 执行前运行或等价执行 `harness_exec_check.py --mode preflight`。
- 实施阶段按 `Stage Contract`、`Stage Entry Gate`、`Stage Exit Gate` 和 `Stage Transition Gate` 执行。
- 实施中发现计划未覆盖的外部事实、API/依赖变化或关键不确定项时，进入 `Research Drift Gate`，补证据或触发 `Plan Amendment Gate`。
- 每个阶段执行 `Development Quality Check`，引用 standards index 复核代码标准、静态质量、架构边界、模式取舍、耦合/内聚和验证证据。
- `run-to-completion` 模式下，阶段完成不是停止条件；仍有 pending stage 时必须继续下一阶段。
- 用户批准实施不等于授权提交，只有明确提交授权时才能 commit。
- managed 任务最终交付必须携带任务结论、验证结果、未覆盖范围、commit 信息和关键证据；前端或可视化任务应提供截图或替代证据。

### process-manager

位置：`skills/process-manager/`

用途：通过本地常驻 Python manager 和 `pm_*` 脚本管理 Windows 长期后台进程，例如 dev server、web 服务、worker、watcher 和动态端口预览服务。

核心约束：

- 只管理长期后台进程，不管理测试、构建、lint、format 等 finite command。
- 启动前先 `pm_health.py`，service config 先 `pm_validate.py`。
- agent 只调用 `pm_*` 脚本，不直接调用 manager API。
- service config 的 `cwd`、可执行程序、脚本和路径类参数必须是绝对路径。
- 顶层不写通用 `host`/`port`；端点放在 readiness 或启动参数里。
- 默认隐藏窗口，stdout/stderr 写入 manager 自动生成的日志文件。
- manager 默认端口是 `18080`；如果绑定失败，会最多向后切换 3 次并把最终端口写回 config。

### gitlab-pat-ops

位置：`skills/gitlab-pat-ops/`

用途：通过 GitLab REST API 和 skill 专属个人访问令牌环境变量，执行项目、仓库、issue、评论和合并请求相关操作。

核心约束：

- 只读取 `SKILL_GITLAB_BASE_URL`、`SKILL_GITLAB_PAT` 和同前缀别名 `SKILL_GITLAB_TOKEN`。
- 默认不读取通用 `GITLAB_TOKEN`，避免和其它 GitLab 工具混用。
- 不确定能力边界、scope 或禁止项时，可运行 `gl_capabilities.py` 查看当前维护的能力清单。
- 先运行 `gl_doctor.py` 检查环境，再执行其它 GitLab 操作。
- 只读能力覆盖项目搜索/详情、仓库 tree/file/raw、GitLab 搜索、issue、notes 和 MR。
- 写操作覆盖项目创建、MR 创建和 issue/MR 评论回复，默认 dry-run，真实请求必须 `--confirm`。
- live 写入 smoke 只允许在 `codex_test` 测试仓库内执行；禁止删除、关闭、合并、force、权限变更、token 管理或批量跨仓库写入。

### electron-ui-verifier

位置：`skills/electron-ui-verifier/`

用途：为 Electron 或浏览器类 UI 任务提供脚本化验证、证据沉淀和问题定位流程。

核心约束：

- 先读取 skill 规则和 references，再执行 UI 验证。
- 验证证据应落到 `.harness` 任务 artifacts、logs 或计划文档中。
- 不把截图、日志和 trace 作为口头结论替代，必须说明覆盖范围和未覆盖范围。

## Repository Layout

```text
skill.sh
skills/
├── complex-coding-planner/
│   ├── SKILL.md
│   ├── scripts/
│   ├── references/
│   └── templates/
├── complex-coding-executor/
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
├── gitlab-pat-ops/
│   ├── SKILL.md
│   ├── agents/
│   ├── scripts/
│   ├── tests/
│   └── references/
├── electron-ui-verifier/
└── process-manager/
    ├── SKILL.md
    ├── scripts/
    ├── references/
    │   └── workflow.md
    └── templates/
examples/
├── complex-coding-harness/   # 历史示例目录
└── process-manager/
evals/
├── complex-coding-planner/
├── complex-coding-executor/
├── gitlab-pat-ops/
└── process-manager/
```

## Install

默认安装会在目标目录已存在同名 skill 时停止，避免混合旧文件：

```sh
./skill.sh install "$HOME/.codex/skills"
```

如需明确替换已有安装，使用 `--force`。该模式会替换目标 skills 目录下与本仓库同名的 skill：

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
