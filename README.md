# dev-skills

本仓库用于沉淀可复用的开发类 skills。

## Skills

### complex-coding-planner

位置：`skills/complex-coding-planner/`

用途：为复杂、长周期、高风险、多阶段或不确定性较高的 coding 任务生成可审批、可验证、可恢复的 task bundle。

核心约束：

- direct 请求轻量处理；managed 请求按风险选择 `lite`、`standard` 或 `full`，高影响未知先进入 discovery-first。
- 同时生成不可变 `execution-plan.md` 和封闭 `plan-contract.json`，用稳定 ID 追踪 requirement、acceptance、stage、validation 与 artifact。
- `Plan Quality Gate` 检查影响面、DAG、覆盖、scope、证据和 amendment trigger。
- `Research Gate` 必须判断不确定项是否为 `none`、`local-only`、`online-required` 或 `blocked-by-access`；涉及可能变化的外部事实时优先查询官方或一手资料。
- `Standards Discovery Gate` 必须识别语言、技术栈、框架、API 类型和架构风险，收集官方/一手或高质量规范来源并形成 standards index。
- `Development Quality Gate` 必须覆盖代码标准、静态质量、架构边界、设计模式取舍、低耦合高内聚和验证映射。
- `Plan Self-Review` 主动复查缺陷、优化点、缺失项、风险和一致性；full/高风险优先 clean-context critique。
- `Readiness Gate` 只表示方案可提交审批，不表示可以自动实现。
- 用户批准前不得进入实现阶段。
- `.harness/active-task.json` 只保存 task pointer；计划中不保存 lifecycle、current stage 或 progress 镜像。
- `harness_plan_check.py --task-dir <dir> --mode approval` 通过后停止等待用户批准；实施交给 `complex-coding-executor`。

### complex-coding-executor

位置：`skills/complex-coding-executor/`

用途：消费 planner 生成并获用户批准的 task bundle，连续执行 stages，并提供可重放状态、崩溃恢复和最终证据门禁。

核心约束：

- 每轮读取 pointer、contract、attestation、append-only ledger 和派生 `run-state.json`；不解析 Markdown 状态。
- 执行前运行 `harness_exec_check.py --mode preflight`，恢复时使用 `status|reconcile`，阶段完成后使用 `transition`。
- 每个开始、attempt、validation、review、stage completion、block、amendment 和 commit 都先追加合法 event，再原子刷新 snapshot。
- 实施中发现计划未覆盖的外部事实、API/依赖变化或关键不确定项时，进入 `Research Drift Gate`，补证据或触发 `Plan Amendment Gate`。
- 每个阶段执行 `Development Quality Check`，引用 standards index 复核代码标准、静态质量、架构边界、模式取舍、耦合/内聚和验证证据。
- validation/review failure 会撤销旧通过证据；ledger 合法而 snapshot 缺失/滞后时才能 reconcile。
- scope、DAG、required validation、风险或授权变化时归档上一 revision，重新批准并用新 ledger 首事件连接旧 hash。
- 阶段完成不是停止条件；只有所有 stage、验证、review、授权、pointer closure 和 final checker 闭环后才能交付。
- 实施授权不等于提交授权；提交必须由 attestation 明确授权并使用 `git commit -F`。

### process-manager

位置：`skills/process-manager/`

用途：通过 workspace-scoped Python manager 和统一 `pm_*` 脚本，在 Windows、Linux、macOS 管理 dev server、Web 服务、worker、watcher 和动态端口预览等长期进程。

核心约束：

- 只管理长期后台进程，不管理测试、构建、lint、format 等 finite command。
- config 不存在时运行 `pm_init.py`；用 `pm_manager.py status|start|stop` 统一管理 manager，不判断 OS/backend。
- service config 只允许 current `direct`/`script` launcher，启动前先 `pm_validate.py`。
- agent 只调用 `pm_*` 脚本，不直接调用 manager API。
- `cwd`、executable/interpreter/script 和 `pathArgs` 必须是绝对路径；禁止 free-form shell。
- readiness、日志、history 和请求均有硬预算；HTTP/TCP 只允许 loopback，manager 端口由 OS 分配。
- stop/restart 必须检查 `cleanupVerified: true` 与 `stopResult.ownerEmpty: true`，绝不按任意 PID 清理。
- 正常流程不先运行 doctor；只有统一操作失败且 capability/selection reason 不清楚时才诊断。

### gitlab-pat-ops

位置：`skills/gitlab-pat-ops/`

用途：通过 GitLab REST API 和 skill 专属个人访问令牌环境变量，执行项目、仓库、label、milestone、成员、分支、issue 模板、issue、评论和合并请求相关操作。

核心约束：

- 认证必填变量只使用 `SKILL_GITLAB_BASE_URL` 和 `SKILL_GITLAB_PAT`；可选 CA、HTTP opt-in 与测试项目边界也使用 `SKILL_GITLAB_*` 前缀，不读取通用或旧 token alias。
- 默认不读取通用 `GITLAB_TOKEN`，避免和其它 GitLab 工具混用。
- 只有不确定能力边界、scope、tier 或禁止项时才精确查询 `gl_capabilities.py`；配置、身份或权限不确定时才 doctor。
- 只读能力覆盖 namespace/project、仓库、commit/branch/template、issue/MR、notes/discussions/events、diff/pipeline/job/approval 等可组合资源。
- 写操作使用统一 preview/fingerprint/preflight guard，覆盖 project/issue/MR 创建、issue/MR metadata 与 close/reopen、note/discussion 回复和 MR thread resolve/reopen。
- live 写入 smoke 只允许在 `codex_test` 测试仓库内执行；禁止删除、合并、approve、force、权限变更、token 管理或批量跨仓库写入。

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
│   ├── agents/
│   ├── scripts/
│   ├── references/
│   ├── templates/
│   └── tests/
├── complex-coding-executor/
│   ├── SKILL.md
│   ├── agents/
│   ├── scripts/
│   ├── references/
│   ├── templates/
│   └── tests/
├── gitlab-pat-ops/
│   ├── SKILL.md
│   ├── agents/
│   ├── scripts/
│   ├── tests/
│   └── references/
├── electron-ui-verifier/
└── process-manager/
    ├── SKILL.md
    ├── agents/
    ├── scripts/
    ├── tests/
    ├── references/
    │   ├── workflow.md
    │   ├── service-schema.md
    │   ├── platform-backends.md
    │   └── security.md
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
