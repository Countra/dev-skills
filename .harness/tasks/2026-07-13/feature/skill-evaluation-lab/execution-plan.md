# Skill Evaluation Lab 执行计划

## 规划摘要（Plan Summary）

- Task ID：`skill-evaluation-lab-20260713`
- Plan revision：`1`
- Lifecycle route：`managed`
- Plan profile：`full`
- Discovery-first：`no`，关键方向已由本地代码、官方资料和 capability 边界收敛；runner 版本漂移留在 STG-03 做 fail-closed probe
- Task contract：`plan-contract.json`
- Approval request：请求 implementation 与有限 live Codex model-run 授权；不请求 commit、external system write 或 elevated tool 授权

本文件只保存批准意图。批准后不写入 current stage、progress、运行结果、ledger 摘要或 commit 状态；执行事实由 executor 创建的 `attestation.json`、`run-state.json` 和 `ledger.jsonl` 保存。

## 问题定义（Problem）

目标（Goal）：`GOAL-01`，交付一个安全、可重复、可审计的 `skill-evaluation-lab`，不仅检查 skill 文件是否合法，还能在显式预算与授权下比较 candidate 与 baseline 的触发、行为、质量和成本。

非目标（Non-goals）：

- 不构建常驻服务、Web UI、数据库或分布式调度。
- 不自动修改被测 skill，也不根据一次 eval 自动发布或提交。
- 不批量重写当前五个 skill 的 eval runner。
- 不依赖进入退役期的 OpenAI Evals API。
- 不支持默认网络、生产外部写入或 danger-full-access case。

验收标准（Acceptance）：`AC-01` 至 `AC-13` 全部由 required `VAL-01` 至 `VAL-15` 闭环；其中 live synthetic evidence 需要用户明确授权模型调用。

约束（Constraints）：

- 遵循仓库 `AGENTS.md`：中文注释、最小变更、完整错误路径、真实验证和长文件分段。
- 核心 runtime 使用 Python 3.12 标准库，跨平台统一 CLI，无后台服务。
- source repo、source skill、oracle、秘密与认证材料不进入可写 case workspace。
- 普通 push/PR CI 不运行付费 live model 或 LLM judge。
- 实施批准与 commit 授权分开；当前没有 commit 授权。

待确认项（Open uncertainties）：无审批阻塞项。Codex activation 没有文档化通用事件，这一外部版本风险已转化为 STG-03 的 synthetic nonce probe 和明确 stop condition，不以假设通过。

## 需求与验收（Requirements And Acceptance）

功能需求：

| ID | Priority | Requirement | Evidence |
| --- | --- | --- | --- |
| REQ-01 | must | closed suite/case/assertion/budget/run contract | AC-01 / VAL-01 |
| REQ-02 | must | 只读 inventory 与静态 coverage | AC-02 / VAL-02 |
| REQ-03 | must | candidate/baseline 快照、隔离和 oracle 防泄漏 | AC-03 / VAL-04 |
| REQ-04 | must | should/should-not trigger、near miss、split、重复与 body-load observation | AC-04 / VAL-07 |
| REQ-05 | must | paired behavior、typed assertion、trusted verifier | AC-05 / VAL-08、VAL-09 |
| REQ-06 | must | Codex CLI JSONL/output-schema/usage/sandbox adapter | AC-06 / VAL-06、VAL-09 |
| REQ-07 | must | deterministic grading、blind judge、human calibration | AC-07 / VAL-10、VAL-11 |
| REQ-08 | must | provenance、delta、区间、成本和 failure taxonomy 报告 | AC-08 / VAL-10、VAL-12 |
| REQ-09 | must | dry-run matrix、硬预算、fingerprint、secret redaction、无隐式 retry | AC-09 / VAL-04、VAL-05 |
| REQ-10 | must | 原子脚本、内聚包、精简 SKILL.md、按需 references | AC-10 / VAL-03、VAL-12 |
| REQ-11 | must | unit/component/mutation/self/live smoke/三平台 offline CI | AC-11 / VAL-14 |
| REQ-12 | must | 现有 eval runner 不变，渐进 inventory 与转换指引 | AC-12 / VAL-02、VAL-13 |
| REQ-13 | must | unsupported/inconclusive/error 不伪装 passed | AC-13 / VAL-06、VAL-11、VAL-15 |

非功能需求：

| ID | Requirement | Validation |
| --- | --- | --- |
| NFR-01 | 标准库、finite process、三平台统一 CLI | VAL-06、VAL-14 |
| NFR-02 | 最小权限、网络关闭、source 只读、路径/秘密 fail closed | VAL-04 |
| NFR-03 | input/oracle 分离、case 公平、重复与人工校准 | VAL-07 至 VAL-11 |
| NFR-04 | 全链路 provenance，跨指纹不聚合 | VAL-04、VAL-05、VAL-10 |
| NFR-05 | timeout、调用/并发/输出上限 | VAL-03、VAL-05、VAL-10 |
| NFR-06 | 高内聚低耦合、closed validation、无巨型脚本 | VAL-01、VAL-08、VAL-12、VAL-15 |
| NFR-07 | Agent Skills/Codex 官方契约，不绑定 Evals API | VAL-01、VAL-03、VAL-06、VAL-13 |

验收标准：

| ID | Requirement IDs | Given / When / Then |
| --- | --- | --- |
| AC-01 | REQ-01 | 合法 suite 通过；mutation suite 返回稳定 JSON path、错误码和非零退出码 |
| AC-02 | REQ-02 | inventory 完整报告五个 skill 与 coverage，且无模型调用或秘密读取 |
| AC-03 | REQ-03 | 独立快照/workspace 带 hash，oracle 不可见，source before/after 不变 |
| AC-04 | REQ-04、REQ-06、REQ-13 | nonce 证明 body-load，输出 trigger 指标；probe 失败为 unsupported |
| AC-05 | REQ-05 | paired run 的 assertion/verifier 给出逐项 PASS/FAIL/ERROR 和证据 |
| AC-06 | REQ-06、REQ-09 | live artifact 有 JSONL/final/usage/provenance，ephemeral、无 case 网络和源写入 |
| AC-07 | REQ-07 | deterministic first；judge 盲化和 swap，冲突 inconclusive，未校准 advisory-only |
| AC-08 | REQ-08 | JSON/Markdown 报告展示质量、成本、区间、低信息和失败分类 |
| AC-09 | REQ-09 | fingerprint/预算/秘密/unknown outcome 任一不安全即调用前拒绝 |
| AC-10 | REQ-10 | skill 能组合最小脚本，全部 help 无认证可用，输出契约一致 |
| AC-11 | REQ-11 | 三平台普通 CI 只跑 offline；live 只有显式入口 |
| AC-12 | REQ-12 | 现有 eval 命令不变并通过，新协议提供示例和转换路径 |
| AC-13 | REQ-13 | 未知 event、probe failure、judge 分歧、provenance 冲突不计 passed |

## 调研门禁（Research Gate）

研究模式（Research mode）：`online-required`

触发原因（Why this mode）：Agent Skills 规范、Codex CLI/config/sandbox、OpenAI eval 生命周期和 2026 benchmark 审计都属于会变化的外部事实；只靠模型记忆无法安全规划。

不确定项清单（Uncertainty inventory）：

| 问题（Question） | 类型（Type） | Online | Resolution | Impact |
| --- | --- | --- | --- | --- |
| Skill 触发如何测量 | external-tool | yes | description 正负例 + body nonce；先做 capability probe | 决定 STG-03 truth source |
| Codex 如何隔离和记录 | external-tool | yes | ephemeral、ignore config/rules、JSONL、output schema、sandbox、skills.config | 决定 runner contract |
| 是否依赖托管 Evals | external-service | yes | 否，旧平台有退役计划 | 采用本地 adapter 架构 |
| LLM judge 是否可信 | high-risk | yes | 仅可选 blind/swap/human-calibrated | 不作唯一硬门禁 |
| benchmark 如何防失真 | high-risk | yes | oracle 隔离、case QA、holdout、污染说明 | 形成 NFR-03 |
| 是否需要后台服务 | local-code | no | 无，finite subprocess 足够 | 降低生命周期复杂度 |

搜索记录（Search log）：

| 查询/来源 | 工具 | 日期 | 结果 | 后续动作 |
| --- | --- | --- | --- | --- |
| Agent Skills specification/evaluating/description/scripts | web | 2026-07-13 | 确认 trigger/outcome eval、baseline、split、脚本契约 | 固化 ART-01/ART-02 |
| Codex non-interactive/config/sandbox | official docs + local CLI | 2026-07-13 | 确认 JSONL、usage、output schema、skills.config 和最小权限 | 设计 Codex adapter |
| OpenAI evaluation best practices/graders | official docs | 2026-07-13 | 确认 pairwise、human calibration、position/verbosity bias | 设计 grading |
| OpenAI 2026 coding eval audits | official research | 2026-07-13 | 发现约 30% benchmark task 问题与污染风险 | 增加 suite QA |
| mattpocock/skills、stitch-skills | local reference repos | 2026-07-13 | 吸收原子编排、frontier probe、artifact loop；排除非标准 metadata 和弱 eval | 形成架构边界 |

来源矩阵：完整 URL、访问日期、可信度和影响见 `ART-01`；所有关键外部结论均来自官方规范、官方文档、官方研究或论文一手资料。

调研结论（Research result）：`passed`。新来源已不再改变目标、候选方案、影响面或 required validation。

## 规范发现门禁（Standards Discovery Gate）

发现模式（Discovery mode）：`online-required`

技术栈清单：

| 类型 | 发现 | 来源 | 影响 |
| --- | --- | --- | --- |
| 语言 | Python 3.12 标准库 | repo CI / Python docs | 统一三平台，无安装依赖 |
| 框架 | Agent Skills 文件协议，无应用框架 | agentskills.io | SKILL.md 渐进披露与合法 metadata |
| API/架构 | 本地 CLI + Adapter + immutable file artifacts | Codex docs / repo patterns | finite process，不建服务 |
| 工具链 | unittest、Git、Codex CLI、GitHub Actions | repository | offline CI 与显式 live 分层 |

规范来源矩阵：

| 规范来源 | 类型 | 官方/一手 | 适用边界 | 访问日期 | 影响 |
| --- | --- | --- | --- | --- | --- |
| `AGENTS.md` | project | yes | 全部改动 | 2026-07-13 | 中文注释、最小修改、验证与提交格式 |
| agentskills.io/specification | framework | yes | skill metadata/resources | 2026-07-13 | name、description、progressive disclosure |
| Google Python Style Guide | language | yes | Python 实现 | 2026-07-13 | 命名、异常、main、docstring |
| Python subprocess/pathlib/secrets/hashlib | language/API | yes | runner/security | 2026-07-13 | argv、timeout、containment、nonce、hash |
| Codex docs | API/security | yes | live adapter | 2026-07-13 | sandbox、env、JSONL、config |
| OpenAI eval guidance + coding eval audits | evaluation | yes | suite/grading/report | 2026-07-13 | 公平 case、人工校准、污染与测试完整性 |

standards index：`ART-02`，记录采用、冲突和明确不采用项。

规范发现结论（Standards result）：`passed`。

## 开发质量门禁（Development Quality Gate）

| Dimension | Plan | Stage mapping | Validation mapping |
| --- | --- | --- | --- |
| 代码标准 | Python 3.12、中文说明性注释、薄 CLI、typed internal API、真实错误处理 | STG-01 至 STG-07 | VAL-01、VAL-03、VAL-15 |
| 静态质量 | quick validate、JSON parse、CLI help、unit、diff check | STG-01、STG-06、STG-07 | VAL-01、VAL-03、VAL-14、VAL-15 |
| 架构边界 | contract/isolation/runner/grading/report 单向依赖 | STG-01 至 STG-05 | VAL-08、VAL-10、VAL-15 |
| 设计模式取舍 | 仅使用 Adapter/Strategy/Artifact Store 的轻量边界；不建插件框架或服务 | STG-03、STG-05 | VAL-06、VAL-10、VAL-15 |
| 低耦合 | runner 不知道 grading，grader 不启动 case，report 只读 artifacts | STG-03 至 STG-05 | VAL-10、VAL-12 |
| 高内聚 | public scripts 只编排，内部模块按契约/安全/runner/评分分组 | STG-01 至 STG-06 | VAL-01、VAL-12、VAL-15 |

过度设计防护：首版只实现 Codex CLI adapter、闭合 assertion 集和文件 artifact；不预建多 provider registry、数据库、UI、队列或通用 workflow engine。模块少于真实职责时允许合并，但不跨越安全与评分边界。

开发质量结论（Development quality result）：`passed`。

## 上下文（Context）

本地代码（Local code）：

- 三个操作型 skill 已证明“薄脚本 + 内部包 + unittest + root eval”适合当前仓库。
- planner/executor eval 强于机器契约，弱于真实代理行为；GitLab prompts 有业务场景但不执行 agent。
- 当前只有两个专用 workflow；新增 lab workflow 不应改写它们。
- `skill.sh` 自动遍历 `skills/*`，新 skill 自动进入安装范围。

本地文档（Local docs）：`README.md`、`CHANGELOG.md`、planner/executor task contract、各 skill SKILL/references、两个参考仓库。完整 change map 见 `ART-06`。

外部来源（External sources）：详见 `ART-01` 和 `ART-02`，核心包括 Agent Skills、Codex non-interactive/config/sandbox、OpenAI eval guidance、2026 coding eval audits 与 MT-Bench judge 论文。

用户约束（User constraints）：深入调研；使用 complex-coding-planner 落盘 detailed plan；当前阶段只规划，不实现；后续按 executor 执行；遵守全局中文注释和验证规则。

证据等级：

| Claim | Level | Source | Impact |
| --- | --- | --- | --- |
| 当前 eval 不运行真实 agent | confirmed | 已读 root eval runners | 新增 live/offline 分层 |
| Codex JSONL 含 usage 和 trace | external | 官方 docs + local help | 可记录 provenance/cost |
| skills.config session override 存在 | external | 官方 config + local help | 可做 candidate/baseline |
| 没有文档化 skill activation event | external | 官方 JSONL event list | 采用 nonce probe，失败即 stop |
| Evals API 不宜成为依赖 | external | 官方 deprecation | 使用本地协议 |
| benchmark 测试自身可能错误 | external | 2026 官方审计 | 增加 suite QA/human calibration |

## 候选方案（Options）

### 方案 A：只补静态 skill 检查

- 做法：统一 quick validation、metadata lint、script help 和现有 eval inventory。
- 优点：实现小、无模型成本、CI 稳定。
- 缺点：无法证明自动触发、行为增益或 token/time 代价。
- 风险：继续把静态 fixture 当成能力证据。
- 验证：纯 unittest/CI。
- 回滚：删除新增检查。

### 方案 B：本地分层 Evaluation Lab（选择）

- 做法：静态/离线能力为基础，再提供显式授权的 Codex paired live adapter、deterministic grading 与可信报告。
- 优点：既保留低成本 CI，也能回答“skill 是否真正有增益”；协议可移植，安全边界明确。
- 缺点：实现和测试较多；activation 需版本探针；live 结果仍有模型漂移。
- 风险：误隔离、成本失控、oracle 泄漏和 judge 偏差；均有 fail-closed gate。
- 验证：VAL-01 至 VAL-15，含 synthetic live smoke。
- 回滚：保留 offline 子集，移除 live adapter。

### 方案 C：托管评测服务或常驻本地服务

- 做法：数据库、队列、Web dashboard 与远程 API 管理实验。
- 优点：适合大规模并发和多人共享。
- 缺点：远超当前五个 skill 的规模，引入部署、认证、迁移和生命周期负担；托管 Evals 平台还有退役风险。
- 风险：扩大秘密和外部写入面，难以在 skill 安装后直接使用。
- 验证：需要新的服务集成和运维体系。
- 回滚：昂贵，不符合最小适用设计。

## 决策（Decision）

选择方案：方案 B。

原因：它是唯一同时覆盖静态合法性、真实触发、行为增益、评测可信度和成本的方案，并可用现有 Python/CLI/repo patterns 落地；通过 offline/live 分层避免把昂贵非确定性任务变成普通 CI 依赖。

影响：新增一个 skill、一个 root self-eval、一个 offline CI workflow、runtime ignore 规则和 README/CHANGELOG 条目；现有 skill runtime 与 eval contract 不变。

可逆性：加法改动；live adapter 可独立回滚，offline inventory/validate/report 仍可使用。

变更条件：只有出现稳定官方 activation event、需要第二 runner、项目规模要求服务化或用户要求迁移现有 eval 时才重新评估架构。

方案变更触发条件：与 `plan-contract.json.reapproval_triggers` 一致，包括公共协议、DAG/VAL、安全边界、依赖、activation truth source、批量迁移和授权范围变化。

## 影响面矩阵（Impact Matrix）

| Surface | Involved | Files/modules | Risk | Validation | Docs |
| --- | --- | --- | --- | --- | --- |
| API | yes | 7 个 `se_*.py` JSON CLI contract | medium | VAL-01、VAL-03 | SKILL/references |
| 数据结构 | yes | suite/run/report schemas | high | VAL-01、VAL-10 | suite-contract |
| 前端交互 | no | none | low | 不适用 | 无 |
| 配置/环境 | yes | Codex flags、env policy、work-dir、budget | high | VAL-04 至 VAL-07 | codex-runner/security |
| 兼容性 | yes | Python 3.12、三平台、Codex capability | high | VAL-06、VAL-14 | workflow/troubleshooting |
| 测试 | yes | skill tests、root self-eval、synthetic fixtures | medium | VAL-01 至 VAL-14 | validation reference |
| 文档 | yes | README、CHANGELOG、SKILL/references | low | VAL-03、VAL-15 | 同左 |
| 代码标准 | yes | 新增 Python 模块和 workflow | medium | VAL-03、VAL-15 | ART-02 |
| 架构设计 | yes | contracts -> isolation -> runner -> grading -> report | high | VAL-12、VAL-15 | ART-03、ART-06 |

## 实施计划（Implementation Plan）

阶段依赖、引用、授权和验证以 `plan-contract.json` 为机器真相源；以下各阶段形成可独立验收的纵向结果。

### STG-01：建立评测协议、CLI 骨架与仓库 inventory

目标：交付不需要模型的最小可用 lab：可以发现仓库 skill、验证 suite、展开 CLI 契约。

做法：建立 `contracts/errors/output/cli/inventory`；实现 `se_doctor.py` offline、`se_inventory.py`、`se_validate.py`、`se_plan.py` 骨架；创建 closed schemas、valid/mutation fixtures 和 public help。

原因：先用 tracer-bullet 打通 contract -> CLI -> fixture -> evidence，后续安全和 live 层只消费稳定模型。

位置：`skills/skill-evaluation-lab/`、`evals/skill-evaluation-lab/`。

参考来源：`ART-01` Agent Skills；`ART-02` Python argparse/json 与 script 规范。

适用规范：非交互、JSON stdout、stderr diagnostic、稳定错误码、unknown field fail closed。

开发质量检查：public scripts 只做参数解析/调用/输出；契约定义唯一；不复制 quick validator；无 live side effect。

验证：`VAL-01`、`VAL-02`、`VAL-03`。

风险和回滚：schema 过宽会掩盖错误，过窄会阻塞扩展；用 mutation fixtures 固化当前契约，后续实质变化走 amendment。回滚整个新目录不影响已有 skill。

阶段契约：

- 依赖：无。
- 需求/验收：REQ-01、REQ-02、REQ-10；AC-01、AC-02、AC-10；NFR-05、NFR-06、NFR-07。
- 允许修改：`skills/skill-evaluation-lab/`、`evals/skill-evaluation-lab/`。
- 禁止修改：`existing skill runtime behavior`、`existing eval runner contracts`、`external systems`。
- 进入条件：approved plan and executor attestation exist；workspace remains on harness/feature with known clean or reconciled changes。
- 退出条件：suite validator and inventory return stable JSON contracts；all public CLI help paths work without live credentials；valid and mutation fixtures pass。
- 必需验证：VAL-01、VAL-02、VAL-03。
- 是否预期提交：none。

### STG-02：实现快照、隔离、安全策略与预算指纹

目标：在任何模型调用前证明 source/secret/oracle 边界和最大成本。

做法：实现 `snapshots/isolation/security/budgets`；规范化 suite + snapshot + runner matrix 计算 SHA-256 fingerprint；复制独立 Git workspace；拒绝 symlink/junction/`..` 逃逸；构造 child env allowlist；unknown outcome 只 reconcile。

原因：隔离是 live runner 的前置能力，不能在 runner 完成后补救。

位置：`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/`、对应 tests/schemas。

参考来源：Codex sandbox/config、Python subprocess/pathlib/secrets/hashlib、ART-03 安全模型。

适用规范：argv + shell false、有限 timeout、显式 cwd/env、source read-only、atomic new run directory。

开发质量检查：路径验证集中实现；redaction 与认证使用分离；budget 是硬 gate，不散落在 CLI。

验证：`VAL-04`、`VAL-05`。

风险和回滚：跨平台 symlink/junction 差异可能误判；用三平台 fixture 与 containment 双重检查。失败时保留 STG-01 offline 能力。

阶段契约：

- 依赖：STG-01。
- 需求/验收：REQ-03、REQ-09；AC-03、AC-09；NFR-02、NFR-04、NFR-05、NFR-06。
- 允许修改：`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/`、`skills/skill-evaluation-lab/tests/`、`skills/skill-evaluation-lab/schemas/`。
- 禁止修改：`source skill contents during a run`、`secret files or secret values`、`danger-full-access execution`。
- 进入条件：STG-01 contract and fixtures pass；snapshot exclusions and work-dir ownership are defined。
- 退出条件：source hashes remain unchanged across fake runs；path escape and secret inheritance mutations fail closed；fingerprint changes on every material matrix or snapshot change。
- 必需验证：VAL-04、VAL-05。
- 是否预期提交：none。

### STG-03：实现 Codex CLI adapter 与真实 trigger observation

目标：用可验证、版本敏感且失败关闭的方式观测 skill body 是否实际加载。

做法：实现 RunnerAdapter/Codex adapter/JSONL parser；先用 `debug prompt-input` 验证 candidate visible 与 baseline hidden；trigger snapshot 只追加随机 nonce body 回执，description 不变；prompt 不含 nonce；用 structured final 精确匹配；记录 CLI/model/config/usage。

原因：self-report 不是 truth source，官方又没有文档化 activation event；nonce 是不会影响触发决策的最小 instrumentation。

位置：`codex_runner.py`、`runners.py`、`traces.py`、tests 与 synthetic fixtures。

参考来源：Codex non-interactive/config docs、Agent Skills progressive disclosure/trigger eval、ART-01。

适用规范：ephemeral、ignore user config/rules、read-only trigger、network off、skills.config session override、secret-free artifact。

开发质量检查：adapter 与 experiment strategy 分离；未知 event 保留但不猜语义；activation probe 连续失败即 stop。

验证：`VAL-06` 为无/低成本 capability doctor，`VAL-07` 在明确模型调用授权后运行 3 positive + 3 near-miss attempts。

风险和回滚：CLI 行为可能漂移；doctor 记录版本和 prompt fingerprint。若 nonce 机制不可靠，不改用回答文本猜测，停止并请求 amendment；offline lab 保留。

阶段契约：

- 依赖：STG-02。
- 需求/验收：REQ-04、REQ-06、REQ-09、REQ-13；AC-04、AC-06、AC-09、AC-13；NFR-01、NFR-02、NFR-03、NFR-04、NFR-07。
- 允许修改：`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/codex_runner.py`、`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/runners.py`、`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/traces.py`、`skills/skill-evaluation-lab/tests/`、`evals/skill-evaluation-lab/fixtures/`。
- 禁止修改：`Codex authentication material`、`production skills for instrumentation`、`model self-report as activation truth`。
- 进入条件：STG-02 security and budget tests pass；user explicitly authorizes finite live Codex model calls before VAL-07。
- 退出条件：debug prompt-input proves candidate visible and baseline hidden；synthetic nonce positive and near-miss negative meet recorded threshold；unsupported capability returns stable fail-closed result。
- 必需验证：VAL-06、VAL-07。
- 是否预期提交：none。

### STG-04：实现 paired behavior runner 与确定性断言

目标：在 pristine candidate 与 baseline 之间执行公平的行为实验，并以可复核机械证据评分。

做法：实现 case pairing、agent-visible copy、output manifest、typed assertions 和 trusted verifier argv；candidate/baseline 使用相同 prompt、fixture、model、sandbox、timeout 和近邻顺序；behavior 不使用 nonce snapshot。

原因：trigger 成功不等于产出有价值，必须证明 skill 相对 baseline 的实际行为增益。

位置：`assertions.py`、`isolation.py`、`se_run.py`、tests 与 behavior fixtures。

参考来源：Agent Skills output eval、OpenAI task-specific eval、ART-03 assertion contract。

适用规范：oracle 不复制、verifier shell=false/timeout/env allowlist、workspace containment、PASS 必须引用证据。

开发质量检查：assertion type 使用 closed dispatcher；verifier 与 runner 分离；candidate/baseline 唯一差异可审计。

验证：`VAL-08`、`VAL-09`。

风险和回滚：baseline 可能也完成简单任务；报告为 low-information，不伪造 improvement。若 live behavior 无授权，stage 保持 blocked 而不是跳过 required evidence。

阶段契约：

- 依赖：STG-02、STG-03。
- 需求/验收：REQ-03、REQ-05、REQ-06、REQ-13；AC-03、AC-05、AC-06、AC-13；NFR-02、NFR-03、NFR-04、NFR-06。
- 允许修改：`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/assertions.py`、`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/isolation.py`、`skills/skill-evaluation-lab/scripts/se_run.py`、`skills/skill-evaluation-lab/tests/`、`evals/skill-evaluation-lab/fixtures/`。
- 禁止修改：`arbitrary shell verifier strings`、`network-enabled behavior cases`、`writes outside isolated case workspace`。
- 进入条件：STG-02 isolated workspace is proven；STG-03 runner produces valid trace/final/usage or explicit unsupported。
- 退出条件：fake and live paired cases keep all variables except skill snapshot constant；typed assertions and trusted verifier emit concrete evidence；oracle leakage fixture is rejected。
- 必需验证：VAL-08、VAL-09。
- 是否预期提交：none。

### STG-05：实现 grading、统计聚合与可信报告

目标：把 run artifacts 转成不掩盖不确定性、成本和评测器缺陷的决策证据。

做法：实现 deterministic grade、blind/swap judge protocol、human feedback merge、Wilson interval、paired delta、token/time 统计、provenance compatibility 和 JSON/Markdown report。

原因：单一通过率或裁判总分会隐藏 baseline、样本量、漂移、成本和 inconclusive。

位置：`grading.py`、`metrics.py`、`reports.py`、`se_grade.py`、`se_report.py` 与 tests。

参考来源：OpenAI evaluation best practices/graders、MT-Bench judge 论文、2026 benchmark audits。

适用规范：deterministic first、A/B 去标识、swap、人工校准、样本不足不伪造方差、跨指纹不聚合。

开发质量检查：grader 只读 artifacts 不重跑 case；metrics 无 runner 依赖；report 只消费规范化模型。

验证：`VAL-10`、`VAL-11`。

风险和回滚：统计过度解释与 judge 偏差；报告强制展示 n、interval、advisory/inconclusive。可完全关闭 judge 而不影响 deterministic pipeline。

阶段契约：

- 依赖：STG-04。
- 需求/验收：REQ-07、REQ-08、REQ-13；AC-07、AC-08、AC-13；NFR-03、NFR-04、NFR-05、NFR-06。
- 允许修改：`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/grading.py`、`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/metrics.py`、`skills/skill-evaluation-lab/scripts/skill_evaluation_lab/reports.py`、`skills/skill-evaluation-lab/scripts/se_grade.py`、`skills/skill-evaluation-lab/scripts/se_report.py`、`skills/skill-evaluation-lab/tests/`。
- 禁止修改：`single opaque overall score`、`unblinded candidate labels for judge`、`aggregation across incompatible provenance`。
- 进入条件：STG-04 run artifacts and assertion evidence are stable；judge remains optional and separately budgeted。
- 退出条件：metrics handle small samples and incompatible provenance correctly；swap conflict is inconclusive；JSON and Markdown reports expose quality, cost, uncertainty and failure taxonomy。
- 必需验证：VAL-10、VAL-11。
- 是否预期提交：none。

### STG-06：完成 skill 工作流、self-eval 与现有 eval 衔接

目标：把模块变成另一个 Codex 能正确触发、按需读取并组合使用的完整 skill。

做法：写精简 `SKILL.md`、`agents/openai.yaml`、workflow/suite/grading/runner/security references、example assets；建立 root self-eval 与 synthetic skill；inventory 给出现有 eval 的 coverage/conversion 建议，保持其命令不变；更新 README/CHANGELOG。

原因：skill 的价值来自可调用工作流，不是脚本数量；references 避免主上下文膨胀。

位置：skill docs/assets、`evals/skill-evaluation-lab/`、`README.md`、`CHANGELOG.md`。

参考来源：Agent Skills progressive disclosure、skill-creator、两个参考仓库的 atomic orchestration/artifact loop。

适用规范：description 同时说明 what/when；body 用祈使流程；reference 一层；不创建 skill 内 README/CHANGELOG 等冗余文件。

开发质量检查：能力列表简洁，只有不确定时读深 reference；脚本组合不固定成一次性场景；示例无真实秘密。

验证：`VAL-03`、`VAL-12`、`VAL-13`。

风险和回滚：description 太宽会误触发，太窄会漏触发；self trigger suite 覆盖正例和 near miss。文档与 eval 可以独立回滚。

阶段契约：

- 依赖：STG-05。
- 需求/验收：REQ-02、REQ-10、REQ-12；AC-02、AC-10、AC-12；NFR-05、NFR-06、NFR-07。
- 允许修改：`skills/skill-evaluation-lab/SKILL.md`、`skills/skill-evaluation-lab/agents/openai.yaml`、`skills/skill-evaluation-lab/references/`、`skills/skill-evaluation-lab/assets/`、`evals/skill-evaluation-lab/`、`README.md`、`CHANGELOG.md`。
- 禁止修改：`bulk migration of existing evals`、`automatic modification of evaluated skills`、`duplicate user-facing documentation inside the skill`。
- 进入条件：STG-05 public behavior and report schema are stable；self-eval fixtures do not contain real credentials or private data。
- 退出条件：SKILL.md remains lean and routes to atomic scripts/references；self-eval demonstrates full fake pipeline and synthetic live path；existing eval commands remain unchanged and pass。
- 必需验证：VAL-03、VAL-12、VAL-13。
- 是否预期提交：none。

### STG-07：完成三平台 CI、代码审查与最终交付证据

目标：证明新增 lab 在仓库公共契约、三平台 offline 环境和实际 Codex smoke 中可用，并完成最终交付复核。

做法：新增 offline matrix workflow 与 runtime ignore；串行运行全部 required VAL；审查安全、评测有效性、架构、文档和 diff；只记录实际 CI/live 状态。

原因：跨平台与评测器可信度必须由独立证据闭环，不能以本地单平台通过代替。

位置：`.github/workflows/skill-evaluation-lab.yml`、`.gitignore`、相关源码/tests/docs。

参考来源：现有两套 workflow、OpenAI automation security guidance、ART-04。

适用规范：ordinary CI 不含 secret/live；contents read；Python 3.12；失败上传 compact evidence；Git 串行。

开发质量检查：审查正确性、路径/秘密/权限、prompt/oracle 泄漏、偏差、错误语义、耦合、重复和过度设计。

验证：`VAL-01` 至 `VAL-15`；`VAL-14` 需要三平台 CI 证据，`VAL-15` 汇总 review 与 `git diff --check`。

风险和回滚：workflow 表达式或平台差异可造成 CI failure；先本地解析/静态检查，再由 Actions 验证，不用 skip 掩盖失败。

阶段契约：

- 依赖：STG-06。
- 需求/验收：REQ-01、REQ-02、REQ-03、REQ-04、REQ-05、REQ-06、REQ-07、REQ-08、REQ-09、REQ-10、REQ-11、REQ-12、REQ-13；AC-01、AC-02、AC-03、AC-04、AC-05、AC-06、AC-07、AC-08、AC-09、AC-10、AC-11、AC-12、AC-13；NFR-01、NFR-02、NFR-03、NFR-04、NFR-05、NFR-06、NFR-07。
- 允许修改：`.github/workflows/skill-evaluation-lab.yml`、`.gitignore`、`README.md`、`CHANGELOG.md`、`skills/skill-evaluation-lab/`、`evals/skill-evaluation-lab/`。
- 禁止修改：`CI secrets in repository files`、`live model calls on ordinary pull_request`、`unrelated repository refactors`。
- 进入条件：STG-06 self-eval and existing eval regression pass；all required live evidence is present or task is explicitly blocked。
- 退出条件：Windows Linux and macOS offline CI contract is valid；all required validations and development quality review pass；diff check is clean and final evidence records actual results without overclaim。
- 必需验证：VAL-01、VAL-02、VAL-03、VAL-04、VAL-05、VAL-06、VAL-07、VAL-08、VAL-09、VAL-10、VAL-11、VAL-12、VAL-13、VAL-14、VAL-15。
- 是否预期提交：final，但当前 commit policy 未授权；获得单独授权后才提交。

## 环境（Environment）

Workspace 环境来源：`.harness/environment.md` 仅作稳定能力参考；其中历史任务动态文字不作为当前活动任务真相，`.harness/active-task.json` pointer 才具有定位权威。

本任务使用：

- Windows PowerShell workspace：`D:/Item/vibe_coding/dev-skills`。
- Git branch：`harness/feature`。
- Python 3.12-compatible stdlib；执行统一加 `-X utf8 -B`。
- Git、Codex CLI `0.144.1` 当前可发现；Actions 使用 Python 3.12。
- live smoke 允许 Codex CLI 自己使用现有认证，但代码不得读取/复制认证内容。

临时覆盖：

- child Codex 使用独立 case workspace、`--ephemeral --ignore-user-config --ignore-rules` 与 session config。
- 所有业务 token/PAT/key 从 child env 移除；case shell env 使用 include-only/none 策略。
- runtime evidence 写 `.harness/test-tmp/skill-evaluation-lab/` 或 task validation artifacts，不提交 raw run。

## Git 上下文（Git Context）

- Main / working branch：当前 `harness/feature`，跟踪 `origin/harness/feature`。
- Task type / branch action：feature managed task；规划阶段不切分支、不 pull、不 push。
- Sync source / occupancy evidence：规划开始时 `git status --short --branch` 为 clean；实施开始由 executor 重新确认。
- Worktree status and known changes：规划文件是当前唯一预期新增；遇到用户新改动时工作并存，不回滚。
- Commit authorization：`not requested`。
- Branch closure：实现完成后只有获得明确 commit 授权才创建 final commit；push/PR 另行授权。

规则：同一仓库 Git 命令串行；只读状态优先 no optional locks。不得自动 stash、rebase、reset、切分支或覆盖未知改动。

## 工具（Tooling）

| Tool | Purpose | Stage | Status | Risk | Alternative | User confirmation |
| --- | --- | --- | --- | --- | --- | --- |
| Python 3.12 | runtime/tests/schema/report | all | required | low | none | implementation approval |
| Git | snapshot metadata/workspace/diff | STG-02、STG-07 | required | medium | filesystem hash only loses repo evidence | implementation approval |
| Codex CLI | capability probe/live runner | STG-03、STG-04 | required for live AC | model cost/external call | fake runner only,不能证明真实能力 | explicit finite model-run approval |
| Agent Skills validator | validate new skill | STG-01、STG-06 | required | low | repo-local equivalent if path unavailable | implementation approval |
| GitHub Actions | 三平台 offline evidence | STG-07 | required | external compute | user push then inspect CI | external action only after separate authorization |
| web/official docs | implementation drift check | amendment only | conditional | changing facts | cached ART-01/ART-02 | new search needs normal network permission |

## 长期进程管理（Process Manager Gate）

- Needs long-running process：`no`。
- Codex run、verifier、test 和 Actions job 都是有 timeout 的 finite command，不进入 process-manager。
- 不启动后台 server、worker、watcher 或队列。
- 若实现中出现常驻服务需求，属于架构变化，必须停止并重新批准；不得用手写后台 shell 绕过 manager。

## 验证（Validation）

| VAL ID | Required | Kind / command / tool | Covers | Evidence path | Failure handling |
| --- | --- | --- | --- | --- | --- |
| VAL-01 | yes | contract unittest | AC-01 / NFR-06、NFR-07 | artifacts/validation/contract-tests.json | 修 contract/fixture 后重跑 |
| VAL-02 | yes | inventory eval | AC-02、AC-12 | artifacts/validation/inventory-evals.json | 修 scanner，不改现有 eval |
| VAL-03 | yes | portable spec validation + all CLI help；官方 validator 可用时做 parity check | AC-10 / NFR-05、NFR-07 | artifacts/validation/skill-and-cli-validation.json | 修 metadata/CLI，差异不静默忽略 |
| VAL-04 | yes | isolation/security unittest | AC-03、AC-09 / NFR-02、NFR-04 | artifacts/validation/isolation-security.json | security failure 立即停止 |
| VAL-05 | yes | budget/fingerprint unittest | AC-09 / NFR-04、NFR-05 | artifacts/validation/budget-fingerprint.json | fail closed |
| VAL-06 | yes | Codex doctor/capability probe | AC-06、AC-13 / NFR-01、NFR-07 | artifacts/validation/codex-probe.json | unsupported 不伪造通过 |
| VAL-07 | yes | 3 positive + 3 near-miss live trigger | AC-04 / NFR-03、NFR-04 | artifacts/validation/live-trigger.json | 授权缺失则 blocked；机制失败触发 amendment |
| VAL-08 | yes | assertion unittest | AC-05 / NFR-03、NFR-06 | artifacts/validation/assertion-tests.json | 修 typed checker |
| VAL-09 | yes | live paired behavior | AC-05、AC-06 / NFR-03 | artifacts/validation/live-behavior.json | 不盲目 retry，先 reconcile |
| VAL-10 | yes | grading/metrics/report unittest | AC-07、AC-08 / NFR-03、NFR-04、NFR-05 | artifacts/validation/grading-metrics-report.json | 修聚合并全量回归 |
| VAL-11 | yes | blind judge protocol unittest | AC-07、AC-13 / NFR-03 | artifacts/validation/blind-judge-protocol.json | conflict 必须 inconclusive |
| VAL-12 | yes | offline self-eval | AC-08、AC-10、AC-12 / NFR-06 | artifacts/validation/self-evals.json | 修 harness/fixture |
| VAL-13 | yes | existing evals unchanged | AC-12 / NFR-07 | artifacts/validation/existing-evals-regression.json | 定位回归，禁止改命令掩盖 |
| VAL-14 | yes | 三平台 offline Actions | AC-11 / NFR-01 | artifacts/validation/cross-platform-ci.md | 按真实平台日志修复 |
| VAL-15 | yes | final development review + diff check | all AC/NFR | artifacts/validation/final-validation.md | finding 修复后重跑相关与全量 |

无法执行的 required 项不得标 passed。尤其 VAL-07/VAL-09 需要 live model authorization，VAL-14 需要用户 push 或外部 Actions 授权；缺失时任务保持 blocked 并说明已有替代证据与残余风险。

## 文档（Documentation）

必需更新：

- `skills/skill-evaluation-lab/SKILL.md`、`agents/openai.yaml`。
- `references/workflow.md`、`suite-contract.md`、`grading.md`、`codex-runner.md`、`security.md`。
- example suite/judge assets；root self-eval 说明。
- 根 `README.md` skill 列表/用途；根 `CHANGELOG.md` 记录新增能力和安全边界。

Changelog 只写实际完成内容，不写 pending commit hash；skill 内不新增 README/CHANGELOG/quick reference 等冗余文档。

## 文件写入策略（File Write Strategy）

| File / group | Segmented | Semantic boundaries | Whole-file check |
| --- | --- | --- | --- |
| SKILL.md/references | yes | frontmatter、workflow、选择/安全/故障 | UTF-8、链接、行数、重复 |
| contracts/schemas | yes | root、case、assertion、artifact | JSON parse、closed fields、fixtures |
| internal Python package | yes | contract、安全、runner、grading、report | imports、unit、中文注释、无循环 |
| tests/evals | yes | unit、component、mutation、synthetic | discover、fixture isolation |
| workflow/docs | local patch | jobs/steps、README section、changelog entry | YAML 静态检查、diff check |

长文件先建框架，再按完整类/函数/章节分段 patch；单次新增控制在 120 行附近、最多 200 行。已有大文件只做局部定点修改，完成后完整重读并检查末尾换行。

## 问题和覆盖项（Questions And Overrides）

| 是否阻塞 | 状态 | 问题 | 决策 | 应用位置 |
| --- | --- | --- | --- | --- |
| no | closed | 是否建服务 | 不建；finite subprocess | GOAL-01、ART-03 |
| no | closed | 是否迁移现有 evals | 保持不变，提供 inventory/conversion | REQ-12、STG-06 |
| no | closed | 如何判断 activation | instrumented body nonce + synthetic capability probe | REQ-04、STG-03 |
| no | closed | 是否默认 LLM judge | 否；可选、另计预算、盲化/swap/人工校准 | REQ-07、STG-05 |
| no | closed | live call 如何授权 | dry-run fingerprint + 当前任务明确 model-run authorization | REQ-09、VAL-07、VAL-09 |

## 方案质量门禁（Plan Quality Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 关键判断有证据等级 | passed | Context evidence table、ART-01 |
| Research Gate 已完成 | passed | ART-01，官方/一手来源和 closed uncertainty |
| Standards Discovery Gate 已完成 | passed | ART-02 |
| Development Quality Gate 已完成 | passed | 本节与 ART-03/ART-04 |
| 影响面矩阵完整 | passed | API/data/config/compat/tests/docs/architecture 全覆盖 |
| 候选方案比较充分 | passed | 静态-only、本地分层、服务化三个可区分方案 |
| 每阶段可独立验证 | passed | 7 个 stage 均有 observable exit 和 VAL |
| 方案变更触发条件清楚 | passed | contract reapproval triggers |
| 用户批准摘要可记录 | passed | Plan Approval 与 Executor Handoff |

质量结论（Quality result）：`passed`。

## 规划自查（Plan Self-Review）

自查结论（Review result）：`passed`。独立 evaluator 未调用，采用 deterministic checker + clean reread/self-critique fallback，结果记录在 `ART-05`。

| Category | Finding | Action | Result |
| --- | --- | --- | --- |
| 缺陷 | 初始想法可能依赖 Evals API | 查到退役时间表 | 改为本地 adapter，closed |
| 优化 | trigger self-report 不可靠 | 设计 nonce instrumentation + probe | closed |
| 缺失项 | 原设计未充分处理 oracle 泄漏和 benchmark flaw | agent-visible/grader-only 分离并增加 suite QA | closed |
| 风险 | auth/业务 token、source write、网络和成本 | env allowlist、sandbox、snapshot、fingerprint | closed |
| 一致性 | plan/contract/artifact ID 与 stage scope 易漂移 | traceability + approval checker | closed |
| 开发质量 | 模块可能过细或过度模式化 | 允许按内聚合并，不跨安全/评分边界 | closed |

门禁重跑：完成 ART-05、ART-06、ART-07 后运行 draft checker；修正全部问题后运行 approval checker。Plan Quality、Self-Review 和 Readiness 均已按最终内容重读。

## 就绪门禁（Readiness Gate）

| Check | Status | Evidence |
| --- | --- | --- |
| 目标和验收清楚 | passed | GOAL-01、REQ/AC tables |
| 上下文已收集 | passed | local repo scan、ART-01、ART-06 |
| 调研门禁已通过 | passed | ART-01 |
| 规范发现门禁已通过 | passed | ART-02 |
| 开发质量门禁已通过 | passed | ART-03、ART-04 |
| 候选方案已比较 | passed | Options A/B/C |
| 决策已记录 | passed | Decision 选择 B |
| 实施阶段已细化 | passed | STG-01 至 STG-07 |
| 环境已确认 | passed | Python/Git/Codex/Actions 及 fallback |
| Git 上下文已确认 | passed | harness/feature、clean baseline、无 commit auth |
| 工具已确认 | passed | Tooling table |
| 验证已确认 | passed | VAL-01 至 VAL-15、授权/阻塞语义 |
| 最终交付证据已规划 | passed | ART-04 required evidence |
| 文档更新已确认 | passed | SKILL/references/root docs |
| 风险已识别 | passed | ART-01 residual、ART-03 security、各 stage rollback |
| 规划自查已通过 | passed | ART-05 + deterministic checker |
| 阻塞问题已关闭 | passed | research unresolved=[]，无开放决策单 |

就绪结论（Readiness result）：`passed`，可以请求用户批准；这不授权实现、模型调用或提交。

## 方案批准（Plan Approval）

状态（Status）：`not_requested`，等待用户审阅本 revision。

批准记录：由用户回复后由 executor/approval gate 写入 attestation，本计划不回写。

批准摘要：

- 批准范围：新增 `skill-evaluation-lab`、root self-eval、offline CI、runtime ignore、README/CHANGELOG；不迁移现有 eval，不改现有 skill runtime。
- 阶段提交授权：未授权；STG-07 final expectation 只有后续明确授权才执行。
- 工具/MCP 授权：请求实施授权；另请求 VAL-07/VAL-09 所需的有限 Codex model calls。GitHub Actions、push、外部写入和提权未授权。
- 文档更新授权：随 implementation scope 请求。

提交策略（Commit policy）：`not_authorized`。

## 方案变更门禁（Plan Amendment Gate）

需要重新批准：

- public CLI、suite contract、error semantics、runner scope 或默认安全边界变化。
- stage 数量/DAG/scope/required VAL 变化。
- 引入第三方依赖、服务、数据库、danger-full-access、默认网络或外部写入。
- nonce activation truth source 无法成立且拟更换机制。
- 批量迁移现有 evals、修改现有 skill runtime 或扩大 model/commit/external/elevated 授权。

无需重新批准：不改变行为的错误文案澄清、测试 fixture 内部命名、执行 evidence、snapshot reconcile 和代码格式修复；由 executor ledger 记录，不改 immutable plan。

## Artifact Index

| ID | Kind | Path | Required | Approval included | Trigger |
| --- | --- | --- | --- | --- | --- |
| ART-01 | research | artifacts/research-findings.md | yes | yes | full + online-required |
| ART-02 | standards | artifacts/standards-index.md | yes | yes | full + Python/Codex/eval standards |
| ART-03 | architecture | artifacts/architecture.md | yes | yes | cross-module/high-risk runner |
| ART-04 | validation | artifacts/validation-strategy.md | yes | yes | nondeterministic/live/cross-platform |
| ART-05 | review | artifacts/plan-critique.md | yes | yes | full clean-context fallback critique |
| ART-06 | other | artifacts/change-map.md | yes | yes | impact/call-path evidence |
| ART-07 | other | artifacts/traceability.md | yes | yes | REQ/AC/NFR/STG/VAL closure |

只列实际创建的 planning artifacts；运行日志、live traces、review 结果和 commit evidence 由 executor 在批准后创建。

## Executor Handoff

- Planner checker：draft 与 approval mode 必须 passed 后才交接。
- Open blocking decisions：none。
- Requested implementation authorization：yes。
- Requested commit authorization：no。
- Requested external-write authorization：no；请求的 Codex model-run 是有限外部调用，不包含外部系统写入。
- Requested elevated-tool authorization：no。
- Residual risks：Codex activation 缺少官方事件、模型/CLI 漂移、私有 holdout 数据治理和三平台 sandbox 差异；均有 probe、provenance、fail-closed 和明确 stop condition。

用户批准后由 executor 生成 attestation 并初始化 run-state/ledger。本文件批准后不可变。
