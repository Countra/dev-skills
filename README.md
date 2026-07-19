# dev-skills

本仓库用于沉淀可复用的开发类 skills。

## Skills

### complex-coding-planner

位置：`skills/complex-coding-planner/`

用途：为复杂、长周期、高风险、多阶段或不确定性较高的 coding 任务生成可审批、可验证、可恢复的 task bundle。

核心约束：

- direct 请求轻量处理；managed 请求按风险选择 `lite`、`standard` 或 `full`，高影响未知先进入 discovery-first。
- 同时生成不可变 `execution-plan.md` 和封闭 `plan-contract.json`，用稳定 ID 追踪 requirement、acceptance、stage、validation 与 artifact。
- Planner producer gate 检查影响面、DAG、覆盖、scope、证据和 amendment trigger，但不生成正式审查 verdict。
- `Research Gate` 必须判断不确定项是否为 `none`、`local-only`、`online-required` 或 `blocked-by-access`；涉及可能变化的外部事实时优先查询官方或一手资料。
- `Dependency Selection Gate` 先判断依赖是否必要，再按 existing stack、标准库/官方方案、生态主流候选和受控专用例外逐级比较；稳定版本、采用规模、更新新鲜度、维护活跃度和采用趋势是正式证据，不能用单一热度指标代替项目适配与 hard gates。
- `Standards Discovery Gate` 必须识别语言、技术栈、框架、API 类型和架构风险，收集官方/一手或高质量规范来源并形成 standards index。
- `Development Quality Gate` 必须覆盖代码标准、静态质量、架构边界、设计模式取舍、低耦合高内聚和验证映射。
- 审批前由 `complex-coding-reviewer` coordinator 按 profile 派生 policy：full=`strict`、lite/standard=`conditional`，显式派发
  一个隔离 Reviewer 子 Agent并生成 dispatch-bound canonical JSON receipt；Planner 只消费通过的回执。
- `Readiness Gate` 只表示方案可提交审批，不表示可以自动实现。
- 用户批准前不得进入实现阶段。
- `.harness/active-task.json` 只保存 task pointer；计划中不保存 lifecycle、current stage 或 progress 镜像。
- `harness_plan_check.py --task-dir <dir> --mode approval` 通过后停止等待用户批准；实施交给 `complex-coding-executor`。

### complex-coding-reviewer

位置：`skills/complex-coding-reviewer/`

用途：以独立的 `plan-review` 和 `code-review` profile，对 managed plan bundle、阶段 delta、最终集成或 standalone 本地代码目标生成可验证的正式审查回执。

核心约束：

- Reviewer 独占正式 review verdict；Planner 负责方案生产与 readiness，Executor 负责实现、验证、修复和 ledger 状态。
- target 支持 managed plan、显式文件、working tree 和 commit range；独立 context manifest 只纳入适用要求、规范和验证证据，任一 digest 变化都会让旧回执 stale。
- 主代理作为 `review-coordinator` 只负责冻结输入、探测 Agent 工具、派发、分段等待、持久化、校验和关闭；一个
  `fork_context=false` 的 `delegated-reviewer` 完成全部语义审查，且不得递归派发、修改文件、运行测试/目标程序或访问网络。
- 单次 Agent 等待不超过 60 秒并持续报告进度，所有轮询共享 preparation 的单一总 timeout，不得重新计时。
- canonical JSON receipt 记录 profile、scope、双 digest、standards、完整 lenses、requirement/risk/path coverage、
  evidence-bound strengths、带 category/origin 的 findings、verification gaps、verdict、限制和 supersedes lineage，并通过
  raw SHA-256 绑定 final dispatch 与原始 semantic result；Markdown 仅为派生视图。
- `plan-review` 与 `code-review` 不混用清单；stage 使用 `stage-delta`，最终提交后使用 execution baseline 到当前 HEAD 的 `final-integration` commit range。
- `plan-review` 检查完整性、一致性、范围和可实施性；`code-review` 先做 spec compliance，再按风险 screen 条件化加载安全隐私、并发完整性、性能资源、API/数据兼容、UI/可访问性/国际化和删除依赖 playbook。
- superseding receipt 必须逐项交代前序 finding；blocking/major finding 或关键 verification gap 未关闭时不能通过。
- full plan、high-risk stage 和 final-integration 使用 `strict`；其它正式审查使用 `conditional`。conditional 在工具可用时仍
  必须委派，只有确认 unavailable/disabled 时才允许 same-context 回退并声明非独立。
- deterministic contract、same-context semantic smoke 和用户 delegated-review observation 分层报告；CI 固定
  `agent_calls=0`，未由用户运行的真实 delegated review 保持 `not_observed`。
- Reviewer 目标只读；只有 coordinator 可通过宿主 Agent 工具派发一个子 Agent。公共 Python CLI 不运行 Agent、模型、网络、
  目标程序、测试或 Git write，只使用标准库，当前契约不提供旧 receipt/payload 的兼容读写。
- 用户可运行 `python -u -X utf8 -B evals/complex-coding-reviewer/run_observation_packet.py --prepare-dir .harness/observations/reviewer` 生成不可执行工作包，再在独立任务中观察正式 Skill 是否恰好派发一个子 Agent，并通过 Skill Evaluation Lab 导入结果；packet 脚本本身不会启动 Agent。

### complex-coding-executor

位置：`skills/complex-coding-executor/`

用途：消费 planner 生成并获用户批准的 task bundle，连续执行 stages，并提供可重放状态、崩溃恢复和最终证据门禁。

核心约束：

- 每轮读取 pointer、contract、attestation、append-only ledger 和派生 `run-state.json`；不解析 Markdown 状态。Planner/Reviewer current checker 只在新批准或 amendment 激活前运行，恢复、transition 和 final 只验证批准时 attestation 的不可变文件 hashes。
- 执行前运行 `harness_exec_check.py --mode preflight`，恢复时使用 `status|reconcile`，阶段完成后使用 `transition`。
- `dependency_selection.mode=none` 时依赖门禁直接返回 `not-applicable`；其它模式精确核对批准的包、来源、选择类别、版本策略和 manifest，并按 critical-runtime/runtime/dev-build 的 30/60/90 天上限要求 task-local runtime receipt。
- 每个开始、attempt、validation、review、stage completion、block、amendment 和 commit 都先追加合法 event，再原子刷新 snapshot。
- 实施中发现计划未覆盖的外部事实、API/依赖变化或关键不确定项时，进入 `Research Drift Gate`，补证据或触发 `Plan Amendment Gate`。
- 每个阶段落实 standards index、代码标准、静态质量、架构边界、模式取舍、耦合/内聚和验证证据，再按 stage risk 将
  `strict|conditional` 交给 Reviewer coordinator；最终集成固定 strict。
- validation/review failure 会撤销旧通过证据；ledger 合法而 snapshot 缺失/滞后时才能 reconcile。
- scope、DAG、required validation、风险或授权变化时归档上一 revision，重新批准并用新 ledger 首事件连接旧 hash。
- 阶段完成不是停止条件；只有所有 stage、验证、阶段回执、提交后的 `final-integration` 回执、授权、pointer closure 和 final checker 闭环后才能交付。
- 实施授权不等于提交授权；提交必须由 attestation 明确授权并使用 `git commit -F`。
- `.github/workflows/planner-executor.yml` 在所有 push/pull request 分支上运行 Windows、Ubuntu、macOS 的三套单测/确定性 eval、Reviewer oracle/static contract、Skill 静态检查、不可执行 observation packet 校验和三 Skill 联合回归；候选验证命令不读取 secrets、不访问网络，也不启动 Agent 或目标应用。

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
