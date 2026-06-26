# Changelog

## 2026-06-26

### Stage 41: complex-coding-harness 分段判断模板优化

- 将 `File Write Strategy` 的行数预测字段改为 `分段判断`，避免把预估行数误当成功能规模约束。
- 明确分段判断是写入风险判断，不是最终内容长度承诺；不得为了符合判断结果删减功能、测试或文档。
- 补充 eval 场景，覆盖无法确定最终行数时使用 `yes/no/unknown` 和分段边界的行为。
- Commit: `pending`
- Commit message: `docs(complex-coding-harness): 优化分段判断模板`

### Stage 40: complex-coding-harness 分段 patch 递进式设计

- 明确分段 patch 不要求一次性生成全部细节，但首次写入前必须有全局框架。
- 允许分模块递进式细化、实现和验证，避免把整体规划误解为一次性全量生成。
- 更新 eval 场景，约束大型模块先明确模块边界、接口关系和验证策略。
- Commit: `3b1f291`
- Commit message: `docs(complex-coding-harness): 精确分段 patch 设计边界`

### Stage 39: complex-coding-harness 分段 patch 语义强化

- 明确分段 patch 是落盘策略，不是思考策略；大内容必须先整体规划，再分段写入。
- 补充全部分段写入完成后的完整文件复查要求，覆盖命名、接口、章节、引用和一致性。
- 增加 eval 场景，约束大型模块不能边写边想，必须先有完整结构和验证策略。
- Commit: `6931e31`
- Commit message: `docs(complex-coding-harness): 强化分段 patch 语义`

### Stage 38: complex-coding-harness 分段 patch 写入策略

- 新增所有大段落盘写文件动作的分段 patch 规则，覆盖代码、文档、规划、模板、eval、changelog 和任务状态。
- 明确单次 `apply_patch` 新增内容建议不超过 120 行、硬上限 200 行，并要求超过 300 行先写分段方案。
- 在执行计划模板中新增 `File Write Strategy` 区块，并补充 4 条 eval 场景覆盖大文档、大代码和 patch 失败恢复。
- Commit: `726e0b2`
- Commit message: `feat(complex-coding-harness): 增加分段 patch 写入策略`

## 2026-06-16

### Stage 37: complex-coding-harness 规划自查门禁

- 新增 `Plan Self-Review` 规划自查规则，要求审批前复查缺陷、优化点、缺失项、风险和一致性。
- 调整执行计划模板审批前门禁顺序为 `Plan Quality Gate`、`Plan Self-Review`、`Readiness Gate`、`Plan Approval`。
- 补充 6 条 eval 场景，覆盖缺失环境、一致性冲突、过度复杂、缺陷阻塞、门禁重跑和顺序错误。
- Commit: `6a7de25`
- Commit message: `feat(complex-coding-harness): 增加规划自查门禁`

## 2026-06-15

### Stage 33: complex-coding-harness 阶段连续执行控制

- 增加 `run-to-completion` 执行模式规则，防止已批准 managed 任务在阶段边界提前停止。
- 在 workflow 中补充停止条件白名单、阶段转移门禁和上下文恢复后的继续执行要求。
- 明确阶段边界只允许进度更新，最终回复只能在停止条件命中或最终交付门禁通过后发送。
- Commit: `8f8c75b`
- Commit message: `feat(complex-coding-harness): 增加连续执行控制`

### Stage 34: complex-coding-harness 执行计划模板状态字段

- 在执行计划模板中新增 `Execution Control`，记录执行模式、剩余阶段、停止条件和状态来源。
- 新增 `Stage Transition Gate`，要求阶段退出后同步 execution plan、active task 并继续剩余阶段。
- 强化 `Resume Summary`，让上下文恢复时以整体目标、剩余阶段和下一步自动动作继续。
- Commit: `21d28cc`
- Commit message: `feat(complex-coding-harness): 增加执行控制模板`

### Stage 35: complex-coding-harness 连续执行评估样例

- 补充阶段边界继续、恢复摘要局部化和阶段提交不是最终交付的 eval 场景。
- 补充明确停止条件、显式 `stage-only` 和阶段进度更新不是最终回复的 eval 场景。
- 补充 `active-task.json` 与 `execution-plan.md` 冲突时以计划为准的 eval 场景。
- Commit: `01f66c4`
- Commit message: `test(complex-coding-harness): 补充连续执行评估`

### Stage 36: complex-coding-harness 执行控制验证收口

- 完成 skill 结构校验、JSONL 解析、关键规则检索和 diff check。
- 回填 harness 执行计划、active task、环境清单和 changelog 的最终状态。
- 确认本任务不涉及长期后台服务，验证命令均为 finite command。
- Commit: `a00cc1f`
- Commit message: `docs(harness): 完成执行控制验证记录`

## 2026-06-12

### Stage 32: process-manager manager 端口重试

- 将 manager 默认端口从 `49321` 调整为 `18080`，避开 Windows 常见动态端口排除范围。
- 增加 `portRetry` 配置，manager 绑定失败时最多向后切换 3 次并把最终端口写回 `config.json`。
- 补充 `pm_init --port` 和 `--port-retry-switches`，并更新模板、文档、eval 和 `.gitignore`。
- Commit: `3c165d4`
- Commit message: `fix(process-manager): 增加 manager 端口重试`

### Stage 31: complex-coding-harness 长期进程门禁

- 将长期后台进程规则升级为 `process-manager` 存在时必须使用的强制门禁。
- 在执行计划模板中新增 `Process Manager Gate`，并接入阶段进入、阶段退出和恢复摘要。
- 补充 eval fixtures，覆盖 dev server、manager 离线、上下文恢复和 finite command 例外场景。
- Commit: `6a00e90`
- Commit message: `docs(complex-coding-harness): 强化长期进程管理规则`

### Stage 30: process-manager bootstrap 空 PID 修复

- 修复 `start_manager.ps1` 在 `manager.pid` 为空时调用 `.Trim()` 失败的问题。
- 修复 `stop_manager.ps1` 遇到空 `manager.pid` 时应返回 `NOT_RUNNING`，避免无效异常。
- 补跑临时 Go Web 项目验证，使用绝对路径 Go 编译 exe 后由 manager 托管启动、HTTP ready、读取 stdout 日志并停止清理。
- Commit: `39b489d`
- Commit message: `fix(process-manager): 修复 manager 空 PID 启动`

### Stage 29: complex-coding-harness 集成说明

- 在 `complex-coding-harness` 中补充长期后台进程优先使用 `process-manager` 的规则。
- 更新 README，补充 `process-manager` skill 用途、约束和仓库结构。
- 扩展 `skill.sh install`，从 `skills/` 安装所有有效 skill；`sh` 不在当前 PowerShell PATH，未执行 shell 语法检查。
- Commit: `153d4dd`
- Commit message: `docs(process-manager): 集成复杂任务 harness 说明`

### Stage 28: process-manager mock lifecycle 示例和评估

- 新增 Python HTTP、worker、动态端口和 Go Web 的 service config 示例。
- 新增 eval fixtures，覆盖长期进程、finite command、顶层 host/port 拒绝、动态端口和 manager 离线场景。
- 使用临时 Python HTTP、worker 和动态端口服务完成 init、validate、start、ready、status、logs、list、stop 生命周期验证；Go 源码已生成但本机未安装 `go`，未执行 Go 运行验证。
- Commit: `1226b53`
- Commit message: `test(process-manager): 补充 lifecycle 示例和评估`

### Stage 27: process-manager Windows bootstrap

- 新增 `start_manager.ps1` 和 `stop_manager.ps1`，用于启动和停止 manager 自身。
- bootstrap 默认隐藏窗口，记录 `manager.pid`，由 manager 自行写 stdout/stderr 日志，避免 PowerShell 重定向长期进程导致阻塞。
- 验证临时 workspace 下 `pm_init`、manager start、`pm_health` 和 manager stop 全流程。
- Commit: `0f016d1`
- Commit message: `feat(process-manager): 增加 Windows manager 启停脚本`

### Stage 26: process-manager pm 脚手架脚本

- 新增 `pm_init.py`、`pm_health.py`、`pm_validate.py`、`pm_start.py`、`pm_ready.py`、`pm_status.py`、`pm_logs.py`、`pm_list.py`、`pm_stop.py`、`pm_restart.py` 和 `pm_doctor.py`。
- 将 manager API 调用封装为短命令，避免 agent 手写 HTTP 请求。
- 验证 CLI help、Python 编译、配置初始化、正向 service 校验、离线 manager 失败输出和顶层 host/port 拒绝。
- Commit: `c3c9b77`
- Commit message: `feat(process-manager): 增加 pm 脚手架命令`

### Stage 25: process-manager manager server 和公共库

- 新增 `pm_common.py`，集中处理 manager 配置、token、service 校验、绝对路径校验、启动器转换和 HTTP 客户端基础能力。
- 新增 `manager_server.py`，提供本地 token 鉴权的 health、list、status、logs、start、ready 和 stop API。
- 支持内部 processKey、自动 runDir/stdout/stderr/pidFile、隐藏窗口启动和通用 readiness 判断。
- Commit: `b81e77b`
- Commit message: `feat(process-manager): 实现 manager 服务核心`

### Stage 24: process-manager skill 骨架和模板

- 新增 `process-manager` skill 的 `SKILL.md` 和 workflow，定义 Windows 长期后台进程管理流程。
- 新增 manager、direct、cmd-file 和 powershell-file JSON 模板，明确绝对路径、隐藏窗口和 readiness 规则。
- 完成 skill 基础校验、JSON 模板解析和关键规则检索。
- Commit: `7d56846`
- Commit message: `feat(process-manager): 新增进程管理 skill 骨架`

## 2026-06-10

### Stage 17: complex-coding-harness skill 更新继续规则

- 增加用户提示 skill 已更新后的重新读取规则。
- 明确不引入 Git tag、版本号或自动迁移流程，避免轻量 harness 变重。
- 补充 eval fixture，约束旧任务状态只在自然更新时按新规则补齐。
- Commit: `cf7e003`
- Commit message: `docs(complex-coding-harness): 增加 skill 更新继续规则`

### Stage 16: complex-coding-harness 提交信息文件规范

- 明确阶段提交必须优先使用 `git commit -F` 读取完整提交信息文件。
- 禁止使用多个 `-m` 参数分别传入 bullet，避免分列之间产生空行。
- 更新执行计划模板、示例和 eval fixtures，覆盖提交信息格式约束。
- Commit: `a70144f`
- Commit message: `docs(complex-coding-harness): 规范提交信息文件方式`

### Stage 15: complex-coding-harness 两阶段门禁文档收口

- 在总规划文档中补充方案制定阶段和方案实施阶段的增强门禁说明。
- README 核心约束补充 `Plan Quality Gate`、`Stage Contract`、`Stage Entry Gate` 和 `Stage Exit Gate`。
- Commit: `6a1423c`
- Commit message: `docs(complex-coding-harness): 记录两阶段门禁增强`

### Stage 14: complex-coding-harness 两阶段门禁评估样例

- 补充弱方案拒绝、阶段进入阻塞、验证失败循环、恢复摘要和范围变更重新审批 eval fixtures。
- 更新 `expected.yaml` 和 eval README，继续声明 fixtures 不是自动判分测试。
- Commit: `c6e6419`
- Commit message: `test(complex-coding-harness): 补充两阶段门禁评估样例`

### Stage 13: complex-coding-harness 验证和审查记录

- 增加验证证据表和验证失败后的修复重验要求。
- 明确 `blocking`、`major`、`minor`、`follow-up` 的 review 处理规则。
- 补充 `Resume Summary`，用于上下文压缩后的快速恢复。
- Commit: `f3d1f57`
- Commit message: `feat(complex-coding-harness): 增强验证和审查记录`

### Stage 12: complex-coding-harness 阶段执行门禁

- 增加 `Stage Contract`、`Stage Entry Gate` 和 `Stage Exit Gate` 规则。
- 执行计划模板新增阶段进入和退出门禁表。
- 示例执行计划补充允许修改和禁止修改范围。
- Commit: `7d32d24`
- Commit message: `feat(complex-coding-harness): 增强阶段执行门禁`

### Stage 11: complex-coding-harness 方案质量门禁

- 增加 `Plan Quality Gate`、证据等级、影响面矩阵和方案变更触发条件。
- 执行计划模板新增批准摘要，示例同步展示方案质量记录。
- Commit: `8f0268c`
- Commit message: `feat(complex-coding-harness): 增强方案质量门禁`

### Stage 10.5: complex-coding-harness 两阶段门禁增强任务托管

- 新增 `.harness` 托管任务计划，记录两阶段门禁增强的方案、Git Context、验证策略和阶段提交规则。
- Commit: `7a0f196`
- Commit message: `docs(complex-coding-harness): 托管两阶段门禁增强任务`

### Stage 10: complex-coding-harness 安装脚本确定性增强

- `skill.sh install` 增加目标目录存在检查，默认拒绝覆盖已有 `complex-coding-harness`。
- 新增 `--force` 安装模式，只替换目标 skills 目录下的 `complex-coding-harness`，并在复制后校验 `SKILL.md`。
- README 补充默认安装、强制替换和运行时任务文件边界。
- Commit: `1d25251`
- Commit message: `feat(complex-coding-harness): 增强 skill 安装脚本`

### Stage 9: complex-coding-harness 模板中文术语统一

- 将环境、执行计划和临时决策单模板调整为中文字段，并保留必要英文术语。
- 同步示例执行计划和临时决策单，避免模板与示例风格漂移。
- Commit: `db7872c`
- Commit message: `docs(complex-coding-harness): 统一模板中文术语`

### Stage 8: complex-coding-harness 工作流评估样例

- 补充 Git Context、热修复插入、最终交付证据和分支占用相关 eval fixtures。
- 更新 eval README，明确当前文件是 prompt fixtures，不是自动判分测试。
- Commit: `1cae648`
- Commit message: `test(complex-coding-harness): 补充工作流评估样例`

### Stage 7: complex-coding-harness 分支收口检查

- 增加固定 harness 分支的分支占用检查和分支收口记录要求。
- 更新执行计划模板和示例，要求最终交付说明代码是否已合回主分支。
- Commit: `9382919`
- Commit message: `feat(complex-coding-harness): 增加分支收口检查`

### Stage 6.5: complex-coding-harness 后续优化规划

- 新增后续优化分阶段规划，覆盖分支收口、eval、模板中文化和安装脚本确定性增强。
- 新增当前任务状态记录，承接用户批准后的分阶段实现流程。
- Commit: `2b7160b`
- Commit message: `docs(complex-coding-harness): 规划后续优化阶段`

### Stage 6: complex-coding-harness 最终交付门禁

- 新增 managed 任务最终交付门禁，要求输出任务结论、验证结果、未覆盖范围、commit 信息和关键证据。
- 补充前端、UI 和可视化任务的截图、日志、trace 或替代证据规则。
- 更新环境和执行计划模板，增加 evidence tools、artifact policy、Executed、Artifacts 和阶段证据字段。
- Commit: `81cbb00`
- Commit message: `feat(complex-coding-harness): 增强最终交付门禁`

## 2026-06-09

### Stage 5: complex-coding-harness Git 工作分支策略

- 新增统一 harness 工作分支策略，按任务类型使用 `harness/feature`、`harness/fix` 等固定分支。
- 补充主分支来源、分支切换安全检查、merge 同步策略和禁止自动 stash/rebase/reset 的约束。
- 增加热修复插入规则：从 feature 切到 fix 前必须确认是否先合并 feature 到主分支。
- 更新 `environment.md` 和 `execution-plan.md` 模板，新增 Git 信息和 `Git Context`。
- Commit: `617b19e`
- Commit message: `feat(complex-coding-harness): 增加统一工作分支策略`

### Stage 2: complex-coding-harness skill 文档实现

- 新增 `skills/complex-coding-harness/SKILL.md`，定义复杂 coding 长任务的触发条件和核心执行约束。
- 新增 `references/workflow.md`，承载 managed 任务分级、方案审批、环境清单、阻塞确认、实施闭环和恢复协议。
- 新增三个模板：`environment.md`、`execution-plan.md`、`pending-decisions.md`。
- 新增仓库 `README.md`，说明当前 skill 位置、用途和核心约束。
- 新增 `examples/complex-coding-harness/`，提供执行计划和临时决策单样例。
- 新增 `evals/complex-coding-harness/`，提供 direct、managed、needs-clarification 和只读规划样例。
- 新增 `skill.sh`，支持从 `skills/` 复制安装 `complex-coding-harness`。
- Commit: `32f969b`
- Commit message: `feat(complex-coding-harness): 实现复杂任务执行 skill`
