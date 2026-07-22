# dev-skills

本仓库用于沉淀可复用的开发类 skills。

## Skills

### complex-coding-planner

位置：`skills/complex-coding-planner/`

用途：为复杂、长周期、高风险、多阶段或恢复敏感的 coding 任务调研并制定精简、可执行、可恢复的方案。

核心约束：

- 按影响面、恢复需求和风险路由为 direct、managed 或 blocked；direct 不创建 Harness 文件。
- managed 任务只维护 `execution-plan.md`、compact `plan-contract.json`、active pointer 和 Executor 创建的 `run-state.json`。
- 只为 stage 与 validation 保留稳定 ID；计划正文不要求固定章节、需求矩阵或 artifact index。
- 本地事实足够时停止调研；时效事实、关键依赖、平台差异和高风险未知优先查询官方一手资料。
- 关键依赖选择仍检查稳定版本、采用规模、维护活跃度、更新时间、趋势和项目适配，但不生成 dependency receipt。
- managed 计划执行人类可读 plan-review；高风险或用户要求时使用一个隔离 Reviewer 子 Agent。
- plan checker 只验证 contract、DAG、scope、validation 和风险边界，不评价文风。
- 用户批准前不得实现；实施、提交、外部写入和提权是不同授权。

### complex-coding-reviewer

位置：`skills/complex-coding-reviewer/`

用途：使用 `plan-review` 和 `code-review` 对明确目标执行只读、证据驱动的工程审查。

核心约束：

- 先检查需求与范围，再检查实现质量；只加载当前风险命中的专业 playbook。
- finding 必须包含严重度、路径与行号、触发条件、影响、证据和有边界的修复方向。
- 普通审查使用当前上下文；高风险或用户要求时创建一个不继承父结论的隔离子 Agent。
- Reviewer 只读，不运行测试、不修改目标；Executor 负责修复和真实验证。
- 结果直接以 findings-first 人类文本返回，不创建 receipt、dispatch、target/context manifest 或其它 JSON。
- 没有 blocking/major 时仍说明 coverage、validation gaps 和残余风险，不输出机械化“零 issue”。

### complex-coding-executor

位置：`skills/complex-coding-executor/`

用途：消费已批准的 compact task bundle，连续执行和恢复 stages，并保持验证、审查及授权边界。

核心约束：

- 首次启动或中断恢复时读取 plan、compact contract、active pointer、run-state 和 Git 事实；阶段内不重复解析全套状态。
- 用户批准后在 run-state 保存 plan/contract digest、独立授权、当前阶段、最近验证、审查摘要和 blocker。
- required validation 或 contract 指定的 review 缺失时不能完成阶段；高风险要求 independent。
- 计划 digest 漂移时停止并重新批准，不生成 amendment 或 revision archive 制品。
- 失败后改变策略，只重跑受影响检查；同一失败命令不得原样执行第三次。
- 有卡死风险的有限命令使用跨平台 `harness_bounded_command.py`；长期服务仍交给 Process Manager。
- Reviewer 结果只以一句摘要记录在 run-state，不保存 findings JSON。
- 提交、外部写入和提权分别要求明确授权；授权提交使用 `git commit -F`。
- CI 在 Ubuntu 运行核心单测和四文件联动测试，并在 Windows、Ubuntu、macOS 验证 bounded-command；不创建 Agent 或上传 artifact。

### process-manager

位置：`skills/process-manager/`

用途：通过 workspace-scoped Python manager 和统一 `pm_*` 脚本，在 Windows、Linux、macOS 管理 dev server、Web 服务、worker、watcher 和动态端口预览等长期进程。

核心约束：

- 只管理长期后台进程，不管理测试、构建、lint、format 等 finite command。
- config 不存在时运行 `pm_init.py`；用 `pm_manager.py ensure|status|restart|stop` 统一管理 manager，并通过 `pm_session.py open|renew|close` 绑定本轮长期进程，不判断 OS/backend。
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

用途：通过本机 Playwright CDP service 验证 Electron UI，执行 typed action/workflow，并生成可校验的 run、report、artifact 和待批准知识资产。

核心约束：

- 只按任务需要读取 server、actions、workflow、knowledge 或 troubleshooting reference，不预加载全部文档。
- 每轮先 prepare；有 appId/goal 时执行紧凑 hybrid retrieval，低置信结果明确 abstain，不补无关 recent assets。
- Playwright 是唯一 driver；mutating action 通过 durable operation 执行，必须有 postcondition，cancel/deadline/unknown outcome 不自动重放。
- 高风险动作使用独立、一次性 risk receipt；风险授权与 knowledge 批准分离，客户端不能自签或绕过服务端复用门禁。
- knowledge 使用 immutable objects、sealed decisions 和可重建 SQLite index；只有 approved decision 引用的 object 才可检索或执行。
- 安装根与 workspace 分离，复制安装保持只读；verifier service 使用统一 process-manager 生命周期并验证 owner-empty cleanup。
- retention 默认只预览，apply 需要未漂移的 exact fingerprint，并保护 active/pending/operation 引用。

### skill-evaluation-lab

位置：`skills/skill-evaluation-lab/`

用途：对 Agent Skill 进行 source-bound 静态检查和七维设计评审，并按需导入用户在独立会话中完成的观察证据，最终由当前 Agent 给出完整结论与优化建议。

核心约束：

- `se_inventory.py` 按需只读盘点 Skill、测试、eval 与 CI coverage；单 Skill 请求不强制全仓扫描。
- `se_check.py` 只解析 metadata、引用、语法、资源和静态能力信号，不 import 或执行目标代码。
- 当前 Agent 按触发边界、工作流、信息架构、工具契约、安全权限、验证交付和可组合性七维完成语义评审。
- 需要运行时证据时，`se_prepare.py` 只生成不可执行 packet，然后停止并等待用户在独立会话中操作。
- `se_import.py` 只校验用户声明、source/case/artifact hash 与 provenance；缺失观察保持 partial/inconclusive。
- `se_report.py` 重新核验当前 candidate/baseline hash，再分开静态事实、审查判断和用户观察；最终结论由当前 Agent 给出。
- 生产代码与 CI 不启动或探测 Codex、模型 API、子代理或其它 Agent，不读取凭据、不运行网络评测。

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
├── complex-coding-reviewer/
│   ├── SKILL.md
│   ├── agents/
│   ├── references/
│   └── tests/
├── gitlab-pat-ops/
│   ├── SKILL.md
│   ├── agents/
│   ├── scripts/
│   ├── tests/
│   └── references/
├── electron-ui-verifier/
├── skill-evaluation-lab/
│   ├── SKILL.md
│   ├── agents/
│   ├── assets/
│   ├── references/
│   ├── schemas/
│   ├── scripts/
│   └── tests/
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
├── complex-coding-reviewer/
├── complex-coding-workflow/
├── gitlab-pat-ops/
├── electron-ui-verifier/
├── process-manager/
└── skill-evaluation-lab/
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
- `skill.sh` 自动发现 `skills/*/SKILL.md`，因此会随其它 skills 一并安装 `complex-coding-reviewer`。
- `.harness/tasks/` 是运行时任务记录，不是 skill 安装产物。
