# Skill Evaluation Lab 用户驱动重构执行计划

## 规划摘要

- Task ID：`skill-evaluation-lab-20260713`
- Plan revision：`3`
- Lifecycle route：`managed`
- Plan profile：`full`
- 变更类型：breaking amendment，不兼容 revision 1
- 目标：把 `skill-evaluation-lab` 从派生 Agent 的 benchmark runner 重构为用户驱动、静态优先、证据分层的
  Skill 评估工作流。
- 核心不变量：生产代码永远不调用、探测或启动 Codex、模型 API、子代理或其它 Agent runtime。
- 用户授权：当前消息明确要求方案完成后按 executor 实施并可提交；不授权 push、外部系统写入或提权。

## Amendment 背景

revision 1 已完成前六个阶段，但最终阶段仍要求两项 live Codex 验证。用户确认该方向
不符合 Skill 职责且风险过高。executor 已记录 `research_drift` 与 `amendment_requested`，并将 revision 1 的 plan、
contract、attestation、ledger、run-state 和 approved artifacts 归档到
`artifacts/amendments/revision-0001/`。

本 revision 改变公共脚本、数据契约、架构边界、Stage DAG 和 required validations。旧 stage 的语义均已发生变化，
因此不继承任何 completed stage；新 attestation 激活后从 STG-01 重新执行。

## 问题定义（Problem）

### GOAL-01

交付一个安全、可重复、可审计的 `skill-evaluation-lab`：当前 Agent 按 Skill 工作流完成静态检查和语义审查，
可选地导入用户独立运行产生的观察证据，最后才综合给出完整结论。

### 范围内

- Skill metadata、目录、引用、渐进披露、语法、能力风险和验证资产的只读静态检查。
- candidate 与可选 baseline 的 source-bound 静态差异。
- 当前 Agent 使用固定维度完成结构化语义 review。
- 生成不可执行的人工 observation packet，由用户自行在独立会话操作。
- 导入并校验用户提供的 observation、artifact hash 和 provenance。
- 分层 JSON/Markdown evidence report、离线 self-eval 和三平台 CI。
- 删除 revision 1 的 runner、live、judge、trace、budget 和兼容协议。

### 范围外

- `codex exec`、Codex capability/version probe、模型 API、子代理、thread 派生或其它 Agent CLI。
- 自动运行目标 Skill、目标脚本、测试、verifier 或 packet case。
- 后台服务、数据库、Web UI、网络评测、外部系统写入和凭据读取。
- 真实触发率、token、duration、paired win rate 或 LLM judge 自动统计。
- 自动修改被评估 Skill，或把报告结论直接写回目标源码。
- 兼容旧 suite/run/grade/report、旧 CLI alias 或 schema version 分支。

## 约束

- 所有新增和修改后的注释、docstring 使用中文。
- 核心 runtime 仅使用 Python 3.12+ 标准库，并保持 Windows、Linux、macOS 同一接口。
- 生产 Python 不 import `subprocess`、socket/HTTP client 或 Agent SDK。
- 目标和 baseline 只读；输出只进入显式 workspace 内评估目录。
- 静态、语义、观察三层证据不能互相覆盖或提升证据等级。
- 当前 Agent 在 report 生成前不得给出整体通过/失败结论。
- 不 push；用户自行推送后观察 hosted Actions。

## 需求与验收

| ID | Priority | Requirement | Acceptance |
| --- | --- | --- | --- |
| `REQ-01` | must | 永久移除所有 Codex、模型、子代理和 Agent 派生执行能力 | `AC-01`：生产树无 Agent runner/doctor/live 入口，AST 安全测试证明无进程和网络执行能力 |
| `REQ-02` | must | 提供只读、source-bound 的 Skill 静态契约检查 | `AC-02`：合法 fixture 生成稳定 evidence，metadata、断链、语法、路径和资源 mutation 均准确 fail/warn |
| `REQ-03` | must | 当前 Agent 必须完成固定七维语义 review | `AC-03`：缺维度、source hash、evidence、limitation 或 warn/fail recommendation 时报告拒绝生成 |
| `REQ-04` | must | 可选生成由用户手工执行的 observation packet | `AC-04`：packet 包含 case/source/input hash 与人工说明，目录不覆盖且不含任何 Agent 启动命令 |
| `REQ-05` | must | 只导入、不执行用户 observation | `AC-05`：有效 bundle 被规范化；未知 case、hash drift、路径逃逸和不完整 provenance 返回稳定错误 |
| `REQ-06` | must | 报告透明分层并由当前 Agent 最终综合 | `AC-06`：report 分开 static/semantic/observed，未观察时禁止 runtime claim，无单一不透明总分 |
| `REQ-07` | must | 支持 candidate 与显式 baseline 的静态比较 | `AC-07`：相同 source 被拒绝，差异绑定双方 tree hash 并按文件/check/capability 分组 |
| `REQ-08` | must | 公共 CLI 与 JSON 契约稳定、有限、跨平台 | `AC-08`：六个 CLI 的 help、合法/非法 envelope、closed schema 和 UTF-8 行为通过三平台离线测试 |
| `REQ-09` | must | `SKILL.md` 体现用户驱动分支和最终完成门禁 | `AC-09`：主路径、可选 observation 路径、停止点、引用加载时机和结论边界与实现一致 |
| `REQ-10` | must | 仓库 inventory、self-eval 和只读 CI 保持可审计 | `AC-10`：inventory/static self-eval 通过，Actions 覆盖三平台、所有分支、只读权限且无 secrets/live |
| `REQ-11` | must | 直接删除旧协议，不保留兼容层 | `AC-11`：旧 CLI、模块、schema、asset、reference、fixture 和测试均消失，全仓无旧公共契约引用 |

## 非功能需求

| ID | Requirement |
| --- | --- |
| `NFR-01` | 生产路径零子进程、零网络、零 Agent SDK、零凭据读取；静态测试将其固化为架构不变量 |
| `NFR-02` | Python 3.12+ 标准库，同一公共接口支持 Windows、Linux、macOS，不依赖 shell 行为 |
| `NFR-03` | 路径 containment、symlink/junction、文件数、单文件、总大小和文本 excerpt 均有硬上限 |
| `NFR-04` | source、packet、review、observation 和 report 使用 SHA-256 绑定，可检测 drift 与证据不兼容 |
| `NFR-05` | 模块高内聚、依赖单向、公共函数有类型标注、错误不吞掉、代码与测试保持现有项目风格 |
| `NFR-06` | `SKILL.md` 保持精炼，详细契约按需进入一层 references，规则只有一个真相源 |
| `NFR-07` | CI 使用最小只读权限、无 secrets、无 package install、无模型/Agent 操作，证据有界保存 |

## 调研门禁（Research Gate）

- 模式：`online-required`。
- 研究结论见 `ART-01`，规范映射见 `ART-02`。
- 已核对 Agent Skills 官方 specification、description optimization、skill evaluation、OpenAI Evals API、本地
  `skill-creator`、`mattpocock/skills` 和 `stitch-skills`。
- 关键结论：保留 case/baseline/assertion/evidence 方法，调度权交给用户；脚本不派生 Agent。
- 未解决事实：无。

## 规范发现门禁（Standards Discovery Gate）

- 语言：Python 3.12+ 标准库；数据：JSON/Markdown/YAML；CI：GitHub Actions。
- 必须规范：项目 AGENTS、当前 planner/executor、Agent Skills specification、Google Python style、JSON Schema
  2020-12 和 GitHub Actions secure use。
- 参考规范：Agent Skills best practices/evaluation、当前 Codex skill-creator、本地两个参考仓库。
- 冲突处理：用户的零 Codex 操作边界优先于官方文档中可选的 subagent/run 自动化建议。

## 开发质量门禁（Development Quality Gate）

- 代码标准：类型标注、聚焦函数、中文注释、稳定错误码、显式资源限制和 `main()` CLI。
- 静态质量：AST、JSON/schema、unit/component/self-eval、quick validator、CLI help 和 `git diff --check`。
- 架构：当前 Agent 编排；static/packet/import/report 单向依赖；无 runner adapter 和后台服务。
- 模式：采用有完成条件的 Pipeline 和 closed document；拒绝为已删除能力保留 Strategy/Plugin 抽象。
- 耦合/内聚：path/hash 单一实现；schema/runtime/example 同步；CLI 薄层；三种证据类型分离。
- 详细映射见 `ART-02`，每个 stage 都必须记录 Development Quality Check。

## 上下文（Context）

- 本地代码：当前 Skill 有 7 个公共 CLI、19 个核心模块、17 个测试文件，主链路会启动 Codex CLI。
- 本地任务：revision 1、2 已归档；revision 3 仅修复 inventory 入口的阶段范围遗漏。
- 本地参考：`mattpocock/skills` 提供 invocation/completion criterion/pruning 思想，`stitch-skills` 提供
  orchestration-agnostic 与确定性 CI validation 思想。
- 外部来源：Agent Skills specification/best practices/evaluation、OpenAI Evals API、Google Python、JSON Schema 和
  GitHub Actions secure use。
- 用户约束：不自动执行任何 Codex 操作；从 Skill 角度设计；用户掌控观察运行；工作流结束后再综合结论。
- 证据等级：本地实现和用户约束为 `confirmed`，官方资料为 `external-primary`，无依赖未验证 assumption。

## 候选方案（Options）

### 方案 A：保留 live runner，只增加更强授权

- 能保留现有 trigger/behavior metrics，实施成本最低。
- 仍然存在递归 Agent、认证继承、权限和额度风险，且用户已否定这一职责。
- 拒绝。

### 方案 B：纯静态 linter

- 安全简单、CI 稳定。
- 无法组织语义审查，也不能承接用户主动提供的真实使用证据，最终结论不完整。
- 不单独采用。

### 方案 C：静态内核 + 当前 Agent review + 用户 observation 导入

- 脚本只做机械事实，Skill 约束当前 Agent，真实运行由用户掌控。
- 保留 prompt/case/baseline/assertion/provenance 的优秀评测方法，不引入 Agent runtime。
- 真实行为证据需要用户额外操作，但证据边界最清晰。
- 选择。

## 决策（Decision）

详细设计见 `ART-03`。公共流程收敛为：

```text
inventory? -> static check -> semantic review -> report -> current Agent conclusion
                                      \
                                       -> prepare packet -> user run -> import -> report
```

公共 CLI 只有：

- `se_inventory.py`
- `se_check.py`
- `se_validate.py`
- `se_prepare.py`
- `se_import.py`
- `se_report.py`

生产代码不出现 `subprocess`、Agent CLI 或模型 API。manual observation packet 是普通 JSON/Markdown 制品，不包含
任何启动指令。报告只产出 evidence summary 和 claim boundary，最终结论由当前 Agent 在工作流末尾完成。

## 影响面矩阵（Impact Matrix）

| Area | Impact | Evidence |
| --- | --- | --- |
| Skill instructions | 完整重写 workflow、references 和 UI prompt | `ART-03`、`ART-04` |
| Public CLI | 删除 doctor/plan/run/grade，新增 check/prepare/import | `ART-04` |
| Data contracts | 删除 run/trace/judge/budget，新增 static/review/observation/report | `ART-03` |
| Python core | 从 Agent runner 重构为只读 parser/checker 和 evidence tools | `ART-04` |
| Tests/evals | 删除 live/fake runner 测试，重建纯静态 fixtures 与 mutation coverage | `ART-06` |
| CI | 三平台保持，但只运行 unit/inventory/static pipeline | `ART-06` |
| Other skills | 不修改；inventory 继续只读识别 | `ART-04` |
| Harness | revision 1、2 归档，revision 3 仅继承语义相同且已完成的前三阶段 | amendment archive |

## 安全与错误策略

- 目标/baseline/input 只读，拒绝 link、`..`、source=output 和覆盖已有 packet。
- 不读取认证目录、环境秘密或用户配置；不需要任何新环境变量。
- Python 语法通过 `ast.parse` 检查，目标模块永不 import。
- capability scan 只报告静态信号，不执行或断言真实副作用。
- closed document 对未知字段 fail closed；建议性规范只产生 warn。
- observation 缺失、stale 或用户 provenance 不完整时保持 `inconclusive`。
- 所有错误输出稳定 code、path、message、guidance 和非零退出码；无隐式 retry。

## 实施计划（Implementation Plan）

### STG-01：移除 Agent runner 并建立静态契约内核

- Depends on：无。
- Covers：`REQ-01`、`REQ-02`、`REQ-07`、`REQ-08`、`REQ-11`；`AC-01`、`AC-02`、`AC-07`、
  `AC-08`、`AC-11`；`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-05`。
- Allowed changes：`skills/skill-evaluation-lab/scripts/`、`skills/skill-evaluation-lab/schemas/`、
  `skills/skill-evaluation-lab/assets/`、`skills/skill-evaluation-lab/tests/`。
- Forbidden changes：`Codex、模型 API、子代理或其它 Agent 派生执行`、`网络、凭据读取或目标 source 写入`、
  `revision 1 兼容 adapter 或 schema 分支`、`其它 Skill runtime`。
- 实施：
  1. 删除 revision 1 runner/live/trace/budget/assertion/grading 模块和公共 CLI。
  2. 建立 safe paths、tree identity、frontmatter/Markdown/resource parser 和 closed contracts。
  3. 实现 candidate/baseline 静态 checks、capability signals 和 transparent delta。
  4. 增加 mutation、资源上限、link/path、AST 和零派生执行测试。
- Required VAL：`VAL-01`、`VAL-02`、`VAL-03`。
- Entry：revision 2 attestation 有效，工作树只有已知 amendment artifacts。
- Exit：旧执行面完全消失，静态 evidence 对合法/非法/baseline fixtures 稳定闭环。
- Risk：high；删除面大，需全仓引用检索和 fail-closed tests。
- Rollback：整体恢复 revision 1 commit；不保留混合协议。
- Commit expectation：none。

### STG-02：实现用户 observation packet 与证据导入

- Depends on：`STG-01`。
- Covers：`REQ-04`、`REQ-05`、`REQ-07`、`REQ-08`；`AC-04`、`AC-05`、`AC-07`、`AC-08`；
  `NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、`NFR-05`。
- Allowed changes：`skills/skill-evaluation-lab/assets/`、`skills/skill-evaluation-lab/schemas/`、
  `skills/skill-evaluation-lab/scripts/`、`skills/skill-evaluation-lab/tests/`。
- Forbidden changes：`自动运行 packet 或任意目标脚本`、`Agent 启动命令、模型配置或凭据`、
  `workspace 外写入或覆盖已有 packet`。
- 实施：
  1. 定义 trigger-positive、trigger-near-miss 和 behavior case 的 closed suite。
  2. 生成带 source/input hash、用户步骤和唯一 fingerprint 的不可覆盖 packet。
  3. 导入用户声明的 session/artifact，验证 packet、case、variant、path 和 hash。
  4. 对 stale、partial、unknown 和 inconclusive 建立明确错误/状态语义。
- Required VAL：`VAL-04`。
- Entry：static identity 和 paths API 已稳定。
- Exit：packet 生成过程无执行能力，合法与 mutation observation fixtures 全部闭环。
- Risk：medium；用户数据和 artifact 路径可能不可信。
- Rollback：删除 packet/import 分支，保留主静态流程。
- Commit expectation：none。

### STG-03：完成语义 review、报告与 Skill 工作流

- Depends on：`STG-01`、`STG-02`。
- Covers：`REQ-03`、`REQ-06`、`REQ-09`、`REQ-11`；`AC-03`、`AC-06`、`AC-09`、`AC-11`；
  `NFR-04`、`NFR-05`、`NFR-06`。
- Allowed changes：`skills/skill-evaluation-lab/SKILL.md`、`skills/skill-evaluation-lab/agents/openai.yaml`、
  `skills/skill-evaluation-lab/references/`、`skills/skill-evaluation-lab/assets/`、
  `skills/skill-evaluation-lab/schemas/`、`skills/skill-evaluation-lab/scripts/`、
  `skills/skill-evaluation-lab/tests/`。
- Forbidden changes：`脚本替当前 Agent 生成语义 finding`、`自动 LLM judge 或 runtime claim 推断`、
  `revision 1 文档与公共入口残留`。
- 实施：
  1. 固定七维 semantic review contract、source binding、evidence 和 limitation 完整性。
  2. 报告分开 static/semantic/observed，生成 claim boundary 和 evidence coverage。
  3. 重写 Skill 主路径、人工 observation 分支、按需 references 和最终完成门禁。
  4. 更新 UI metadata，确保默认 prompt 不再提 live/model authorization。
- Required VAL：`VAL-05`、`VAL-09`。
- Entry：static 与 observation documents 已稳定。
- Exit：缺任一必需 review 维度时 fail closed；完整报告后当前 Agent 才能形成结论。
- Risk：medium；过度自动化语义判断会再次越界。
- Rollback：保留静态 evidence，回退 report/workflow 层。
- Commit expectation：none。

### STG-04：重建离线 self-eval 与三平台 CI

- Depends on：`STG-03`。
- Covers：`REQ-08`、`REQ-10`、`REQ-11`；`AC-08`、`AC-10`、`AC-11`；`NFR-01`、`NFR-02`、
  `NFR-03`、`NFR-07`。
- Allowed changes：`skills/skill-evaluation-lab/tests/`、`evals/skill-evaluation-lab/`、
  `.github/workflows/skill-evaluation-lab.yml`、`skills/skill-evaluation-lab/scripts/se_inventory.py`、
  `skills/skill-evaluation-lab/scripts/skill_evaluation_lab/inventory.py`。
- Forbidden changes：`GitHub secrets、network eval 或 package install`、`Codex、模型或其它 Agent command`、
  `push 或其它 workflow 行为`。
- 实施：
  1. 删除 fake/live runner fixture，建立 valid/invalid/baseline Skill 和 observation mutation fixtures。
  2. 重写 inventory 与 static workflow self-eval，输出有界 evidence。
  3. 更新三平台 Actions 命令和 artifact paths，保持所有分支触发与 `contents: read`。
  4. 增加 CI contract test，明确生产代码无进程/网络能力且 workflow 无 live/secrets。
- Required VAL：`VAL-06`、`VAL-07`、`VAL-08`、`VAL-10`、`VAL-11`。
- Entry：所有公共 CLI、schema 和工作流文档已稳定。
- Exit：本地完整复现 CI 命令，self-eval 明确 `agent_calls=0`、`network_calls=0`。
- Risk：medium；fixture 或 Actions path 漂移会造成三平台失败。
- Rollback：恢复上一离线 workflow；不能恢复 live CI。
- Commit expectation：none。

### STG-05：最终审查、回归与提交

- Depends on：`STG-04`。
- Covers：`REQ-01`、`REQ-02`、`REQ-03`、`REQ-04`、`REQ-05`、`REQ-06`、`REQ-07`、`REQ-08`、
  `REQ-09`、`REQ-10`、`REQ-11`；`AC-01`、`AC-02`、`AC-03`、`AC-04`、`AC-05`、`AC-06`、
  `AC-07`、`AC-08`、`AC-09`、`AC-10`、`AC-11`；`NFR-01`、`NFR-02`、`NFR-03`、`NFR-04`、
  `NFR-05`、`NFR-06`、`NFR-07`。
- Allowed changes：`approved skill-evaluation-lab scope problem fixes`、
  `task-dir executor evidence and lifecycle files`、`final authorized Git commit`。
- Forbidden changes：`new feature expansion or old protocol restoration`、
  `push、external write or elevated tool`、`modification of archived revision 1`。
- 实施：
  1. 运行全量 lab tests、两套 self-eval、quick validator、CLI/schema/AST checks。
  2. 运行 planner/executor harness 回归与 amendment/final checker。
  3. 执行代码审查，重点验证无派生执行、证据等级、路径边界、错误语义和文档一致性。
  4. 检查工作树范围、旧引用、凭据模式、`__pycache__`、行长和 `git diff --check`。
  5. 使用单个 `git commit -F` 提交，写 `commit_recorded`，闭合任务并关闭 active pointer。
- Required VAL：`VAL-12`、`VAL-13`，并重跑 `VAL-06`、`VAL-08`。
- Entry：STG-01 至 STG-04 完成且无 blocking finding。
- Exit：所有 required VAL 与 review 通过，提交已记录，executor final checker 通过。
- Risk：medium；大规模删除可能存在陈旧引用或 evidence 盲点。
- Rollback：提交前定点修复；提交后整体 revert 单一 commit。
- Commit expectation：final。

## 验证（Validation）

| ID | Kind | Required | Coverage | Command/Process |
| --- | --- | --- | --- | --- |
| `VAL-01` | test | yes | `AC-02`、`AC-08`、`NFR-03`、`NFR-05` | 运行 contracts/parser/path 单元测试与 mutation fixtures |
| `VAL-02` | test | yes | `AC-01`、`NFR-01` | 运行 `test_no_agent_execution.py`，AST 证明生产树无 subprocess/network/Agent runtime |
| `VAL-03` | test | yes | `AC-02`、`AC-07`、`NFR-04` | 运行 static checks、candidate/baseline delta 和 source drift tests |
| `VAL-04` | test | yes | `AC-04`、`AC-05`、`NFR-03`、`NFR-04` | 运行 packet/observation component 与 path/hash mutation tests |
| `VAL-05` | test | yes | `AC-03`、`AC-06`、`AC-09`、`NFR-06` | 运行 semantic review completeness、report claim boundary 和 reference tests |
| `VAL-06` | test | yes | `AC-08`、`AC-10`、`NFR-02` | 全量 `unittest discover` |
| `VAL-07` | eval | yes | `AC-10` | 运行 inventory self-eval，确认现有 Skill coverage 和零 Agent/network 调用 |
| `VAL-08` | eval | yes | `AC-02` 至 `AC-07`、`AC-10` | 运行 static workflow self-eval，闭合 check/review/report 和可选 import fixture |
| `VAL-09` | lint | yes | `AC-09`、`NFR-06` | skill-creator quick validator 与 `agents/openai.yaml` 同步审查 |
| `VAL-10` | lint | yes | `AC-08`、`NFR-02`、`NFR-05` | 六个 CLI `--help`、生产 Python AST parse、schemas/assets JSON parse、行长检查 |
| `VAL-11` | build | yes | `AC-10`、`NFR-07` | CI contract test，并在本地执行 workflow 对应 unit/inventory/static 命令 |
| `VAL-12` | regression | yes | amendment 与 harness 正确性 | planner/executor unit、eval、approval/preflight/transition/final checker |
| `VAL-13` | review | yes | 全部 AC/NFR | 最终 code review、旧引用/secret/pycache 检索、范围检查和 `git diff --check` |

具体命令、预期证据和替代路径见 `ART-06`。Hosted 三平台 Actions 需要用户 push，属于提交后的观察项，不作为本地
提交前 required VAL，也不得为此自动 push 临时 ref。

## 环境（Environment）

- Workspace：`D:/Item/vibe_coding/dev-skills`，稳定事实见 `.harness/environment.md`。
- Runtime：本地 Python 3.13.12；公共兼容目标 Python 3.12+；Git 2.53.0.windows.2。
- Package manager：无；不下载或安装依赖。
- Runtime service：无。
- 临时输出：`.harness/test-tmp/skill-evaluation-lab/`，验证后清理。
- 认证与环境变量：不需要且不得读取。

## Git 上下文（Git Context）

- 当前分支：`harness/feature`；不切分支、不 stash、不 rebase、不 reset。
- revision 1 的两个已提交 commit 保留；本 revision 在其上新增一个 breaking refactor commit。
- 同一仓库 Git 命令串行；提交前检查 status、diff、diff-check 和 staged scope。
- 用户已授权最终 commit，未授权 push、external write 或 elevated tool。
- 提交使用 `git commit -F <message-file>`，标题后一个空行，bullet 之间无空行。

## 工具（Tooling）

- 允许工具：PowerShell、Python、Git、`apply_patch`、在线官方资料查询。
- 禁止工具：`codex` 命令、模型 API、subagent/thread 派生、后台服务和 package auto-install。
- 本任务无长期进程，不进入 process-manager。

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`no`。
- 所有 validation 都是有 timeout 的 finite command，不启动服务、worker、watcher 或 dev server。
- 若实现意外需要长期进程，属于 plan drift，必须 amendment；不得手写后台 shell。

## 文档（Documentation）

- 必需更新：`SKILL.md`、`agents/openai.yaml` 和五个按需 references，与当前唯一 CLI/schema 同步。
- 必需删除：Codex runner、live grading、judge、budget、trace 和旧协议文档。
- README/CHANGELOG：仅在仓库入口失真时定点修改；当前计划不产生无关发布文档变更。
- Runtime packet/report 是用户工作制品，不放入 Skill 源码或 Git 提交。

## 文件写入策略

- planning artifacts、plan 和 contract 已按完整章节分段 patch；大文件不整段单次重写。
- 实施阶段优先删除失效模块后按模块新建，每个 patch 保持类/函数/配置对象完整。
- schema 和 runtime validator 分文件更新，随后立即运行 parse/contract tests。
- 不生成或提交 `__pycache__`、runtime packet、self-eval 临时目录或 active pointer。

## 问题和覆盖项（Questions And Overrides）

| ID | Blocking | Status | Decision | Applied to |
| --- | --- | --- | --- | --- |
| `Q-01` | no | resolved | 不保留任何自动 Codex/Agent 评测入口 | `REQ-01`、`NFR-01`、`VAL-02` |
| `Q-02` | no | resolved | 真实观察由用户独立运行，Skill 只生成 packet 和导入 evidence | `REQ-04`、`REQ-05` |
| `Q-03` | no | resolved | 不兼容 revision 1，amendment 不 carry stage | 所有 stages、`REQ-11` |
| `Q-04` | no | resolved | Hosted Actions 由用户 push 后观察，本地不自动 push | `VAL-11`、最终交付 |

## 方案质量门禁（Plan Quality Gate）

- 一手资料支持用户驱动、独立会话、机械断言和渐进披露决策。
- 比较了保留 runner、纯 linter 和分层工作流三种可区分方案。
- change map 覆盖公共入口、模块、schema、assets、tests、evals、CI 和删除面。
- 所有 must REQ 均有 AC、stage 和 required VAL；所有 NFR 均进入 stage/VAL。
- breaking behavior、回滚、权限、Git、三平台和用户 observation 停止点明确。
- 无未解决决策、秘密、外部服务或长期进程 blocker。

## 规划自查（Plan Self-Review）

- 缺陷修复：撤销“授权即可安全派生 Codex”的错误前提。
- 优化：删除 runner/trace/budget/judge/statistics 过宽架构，公共 CLI 从 7 个收敛为 6 个确定性入口。
- 缺失补全：新增当前 Agent semantic review、用户 packet、observation import 和 final synthesis gate。
- 风险修复：生产树以 AST contract 禁止进程/网络能力，CI 不含 secrets 或 live 分支。
- 一致性：revision 1、2 已归档；revision 3 只 carry 语义完全相同的 STG-01 至 STG-03；其它 IDs 和范围不变。
- 降级说明：未使用独立 Agent critique，因为用户禁止自动派生 Agent；以官方资料、deterministic checker 和
  structured self-review 替代，不伪造 clean-context review。

## 就绪门禁（Readiness Gate）

- Research、Standards、Development Quality、Change Map、Traceability、Validation Strategy 已闭环。
- `harness_plan_check --mode draft|approval` 必须通过后才能生成新 attestation。
- 用户当前消息明确授权完成该重构和最终提交；revision 3 只纠正 inventory 文件的阶段归属，不扩展用户可见范围。
- attestation：implementation=true、commit=true、external_write=false、elevated_tool=false。
- 激活 amendment 时不 carry revision 1 stage，current ledger 从 `amendment_approved` 开始。

## 方案批准（Plan Approval）

批准将 `skill-evaluation-lab` 直接重构为用户驱动的静态评估 Skill：删除全部 Codex/Agent live runner、probe、
budget、trace、judge 和旧协议；新增静态检查、当前 Agent 七维语义 review、用户 observation packet/import、透明
报告、离线 self-eval 和三平台 CI。授权实施与最终 `-F` commit；不授权 push、外部写入或提权。

## 方案变更门禁（Plan Amendment Gate）

- 拟恢复或新增任何 Codex、模型 API、子代理、Agent CLI、进程执行或网络能力。
- required evidence layers、七维 review、公共 CLI、schema、Stage DAG 或 required VAL 实质变化。
- 需要自动执行目标 Skill/脚本/test/verifier，或写入目标/baseline source。
- 引入第三方依赖、后台服务、数据库、凭据、外部系统写入、提权或 push。
- 需要兼容 revision 1 或批量修改其它 Skill/runtime。

## 停止条件（Stop Conditions）

- 检测到任何生产路径可能启动 Agent/进程、访问网络或读取凭据。
- source/output containment、link、hash 或 observation provenance 无法 fail closed。
- 实现需要超出 approved scope，或旧协议删除影响未确认的外部消费者。
- required validation 在有界修复后仍失败，或 review 存在 blocking/major finding。
- attestation/hash/ledger/run-state 不一致，或用户暂停/撤销授权。

## Artifact Index

| ID | Kind | Path | Approval included |
| --- | --- | --- | --- |
| `ART-01` | research | `artifacts/research-findings.md` | yes |
| `ART-02` | standards | `artifacts/standards-index.md` | yes |
| `ART-03` | architecture | `artifacts/architecture.md` | yes |
| `ART-04` | other | `artifacts/change-map.md` | yes |
| `ART-05` | other | `artifacts/traceability.md` | yes |
| `ART-06` | validation | `artifacts/validation-strategy.md` | yes |
| `ART-07` | review | `artifacts/plan-critique.md` | yes |

## Executor Handoff

1. 校验 revision 3 approval 与 attestation。
2. 使用 `activate-amendment` 且不传 `--carry-stage`，生成新 ledger/run-state。
3. 按 STG-01 至 STG-05 连续执行；每阶段记录 Development Quality Check、review、VAL 和 transition。
4. STG-05 提交后记录真实 commit，追加 completed，关闭 active pointer。
5. 用显式 task-dir 运行 final checker，确认 revision 3 completed 后再向用户汇报。
