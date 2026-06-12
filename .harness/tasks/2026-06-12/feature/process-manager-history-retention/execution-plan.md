# 执行计划（Execution Plan）

## 问题定义（Problem）

目标（Goal）:

- 为 `process-manager` 增加可靠的历史记录保留策略，避免 `processes.json` 和 `runs/` 随长期使用无限膨胀。
- 调整 `pm_list.py` 的默认输出，让日常查看聚焦当前活跃和运行中进程，完整历史必须显式请求。
- 在 `process-manager` skill 中固化历史裁剪、`runs/` 同步删除和安全边界。
- 联动更新 `complex-coding-harness`，让它知道 `process-manager` 的历史记录会被裁剪，必要证据必须及时沉淀到任务记录或 artifacts 中。

非目标（Non-goals）:

- 不重新设计 manager 的 HTTP API 架构。
- 不改变 `process-manager` 只支持 Windows 的当前约束。
- 不把 finite command 纳入 `process-manager`。
- 不新增跨平台守护进程、数据库、GUI 或外部依赖。
- 不实现任意 PID 清理或未知进程 kill。

验收标准（Acceptance）:

- `processes.json` 默认只保留所有 `running`、所有 `stop_timeout` 和最近 20 条 inactive 记录。
- 被自动裁剪的 inactive 记录，对应的精确 `runDir` 默认同步删除。
- `pm_list.py` 默认输出 `active` 和 `running`；只有 `--history` 才输出保留后的 `processes` 历史。
- 自动裁剪永远不删除 `running` 和 `stop_timeout`。
- 删除 `runDir` 前必须确认路径位于 `.harness/process-manager/runs/<service>/<processId>/`，不能删除 `runs/`、`runs/<service>/` 或任意外部路径。
- `process-manager` 的 `SKILL.md`、`references/workflow.md`、模板、示例或 eval 体现新规则。
- `complex-coding-harness` 的长期进程门禁补充证据保留规则，避免长期任务把即将被清理的 runDir 当作唯一交付证据。

约束（Constraints）:

- 遵守最小变更原则，优先复用现有 `manager_server.py`、`pm_common.py` 和 `pm_*` 脚本模式。
- 不引入第三方依赖。
- 中文文档和必要中文注释。
- 不能删除用户运行中的进程，不能清理未知路径。
- 如果实现阶段发现状态模型与计划不一致，必须更新计划并重新确认。

待确认项（Open uncertainties）:

- 无 blocking 待确认项。默认采用全局 `maxInactive = 20`，默认 `deleteRunDirs = true`。

## 上下文（Context）

本地代码（Local code）:

- `skills/process-manager/scripts/manager_server.py`：当前 `/processes` 返回 `active` 和完整 `processes`；`status()`、`list_processes()`、`stop()` 会刷新状态并保存。
- `skills/process-manager/scripts/pm_common.py`：当前 `ManagerConfig` 包含端口、路径和重试配置；尚无 history 配置。
- `skills/process-manager/scripts/pm_list.py`：当前无 `--history`，直接打印 `/processes` 返回内容。
- `skills/process-manager/templates/manager-config.json`：当前无 `history` 字段。
- `skills/complex-coding-harness/references/workflow.md`：已强制长期进程使用 `process-manager`，但未说明历史记录裁剪和证据保留。
- `skills/complex-coding-harness/templates/execution-plan.md`：已有 `Process Manager Gate`，但未记录日志证据需要复制或摘录到任务 artifacts。

本地文档（Local docs）:

- `skills/process-manager/SKILL.md`：当前描述 `pm_list.py` 为列出 known 和 active processes，未说明默认视图和历史上限。
- `skills/process-manager/references/workflow.md`：当前说明 runtime 目录和 `processes.json`、`runs/` 都是运行产物，未说明自动裁剪策略。
- `.harness/environment.md`：记录本仓库是 skill 源码仓库，runtime artifact 默认忽略。

外部来源（External sources）:

- 本阶段不依赖在线资料；该变更属于本地工具状态管理和安全删除策略。

用户约束（User constraints）:

- `processes` 不应无限增长。
- 最早的非活跃记录从 `processes` 删除时，应同步删除对应的 `runs` 内容，因为二者一一对应。
- `running` 和真实仍运行的进程不能被自动删除，避免留下 manager 管不到的孤儿进程。
- 方案需要用 harness 管理，并明确相关 skill 是否需要调整。

证据等级（Evidence levels）:

| 结论（Claim） | 等级（Level） | 来源（Source） | 影响（Impact） |
| --- | --- | --- | --- |
| 当前 `/processes` 返回完整历史 | read | `manager_server.py:list_processes()` | 需要修改默认 list 输出和 API 查询参数 |
| 当前 `pm_list.py` 没有历史筛选参数 | read | `pm_list.py` | 需要新增 `--history` |
| 当前 manager config 无 history 配置 | read | `pm_common.py`、`templates/manager-config.json` | 需要扩展配置解析和模板 |
| `runs/` 和 `processes.json` 都是 ignored runtime artifact | read | `.gitignore`、`workflow.md` | 自动删除不会影响 Git 跟踪文件 |
| `complex-coding-harness` 已有长期进程门禁 | read | `complex-coding-harness` workflow/template | 只需轻量补充证据保留和 `pm_list` 行为 |

## 候选方案（Options）

### 方案 A：只改 `pm_list` 展示，不裁剪历史

- 做法（How）:
  - `pm_list.py` 默认只显示 running，`--history` 显示完整 `processes`。
  - 不删除 `processes.json` 中的旧记录，不删除 `runs/`。
- 优点（Pros）:
  - 风险最低，不涉及删除文件。
  - 实现最小。
- 缺点（Cons）:
  - `processes.json` 和 `runs/` 仍会无限增长。
  - 不能解决用户关心的长期堆积问题。
- 风险（Risks）:
  - 只是隐藏问题，不是治理问题。
- 验证（Validation）:
  - 验证默认输出不含历史。
- 回滚（Rollback）:
  - 回退 `pm_list.py`。

### 方案 B：只提供手动 `pm_prune.py`，不自动裁剪

- 做法（How）:
  - 新增 `pm_prune.py --dry-run/--apply`。
  - 用户需要时手动清 inactive 和 runDir。
- 优点（Pros）:
  - 删除行为显式，风险可控。
  - 适合保守审计场景。
- 缺点（Cons）:
  - 日常使用仍会堆积，agent 也容易忘记手动 prune。
  - `pm_list` 仍可能越来越吵。
- 风险（Risks）:
  - 清理依赖人工或 agent 记忆，不符合稳定自动托管目标。
- 验证（Validation）:
  - 验证 dry-run、apply、路径安全。
- 回滚（Rollback）:
  - 删除 `pm_prune.py` 或禁用调用。

### 方案 C：默认轻量展示 + 自动裁剪 inactive + 同步删除 runDir

- 做法（How）:
  - 在 config 增加 `history.maxInactive = 20` 和 `history.deleteRunDirs = true`。
  - 每次刷新状态后自动裁剪历史，只保留所有 `running`、所有 `stop_timeout` 和最近 20 条 inactive。
  - 被裁剪 inactive 的精确 `runDir` 同步删除。
  - `pm_list.py` 默认只输出 `active` 和 `running`；`--history` 才输出保留后的 `processes`。
  - 新增或预留 `pm_prune.py` 做手动 dry-run 和强制清理。
- 优点（Pros）:
  - 日常输出清爽。
  - JSON 和磁盘运行目录都不会无限增长。
  - 不依赖 agent 记忆手动清理。
  - 仍保留最近 20 条 inactive 便于排查。
- 缺点（Cons）:
  - 默认删除旧 runDir，必须做好路径安全和证据保留规则。
  - 对依赖很久以前日志的调试场景，需要提前复制证据。
- 风险（Risks）:
  - 路径校验不严会造成误删。
  - 自动清理可能删除用户想保留的旧日志。
- 验证（Validation）:
  - 用临时 workspace 生成超过上限的 inactive 记录，确认 JSON 和 runDir 同步裁剪。
  - 验证 running、stop_timeout 不被裁剪。
  - 验证外部 runDir 不会被删除。
- 回滚（Rollback）:
  - 将 `history.maxInactive` 调大或禁用自动 prune；回退代码后保留现有 JSON 不影响运行中进程。

## 决策（Decision）

选择方案（Chosen option）:

- 方案 C：默认轻量展示 + 自动裁剪 inactive + 同步删除 runDir。

原因（Why）:

- 用户明确希望 `processes` 不要无限增长，并认可被踢出的非活跃记录和对应 `runs` 一起删除。
- `process-manager` 的目标是稳定托管长期进程，清理策略必须内置，不能依赖 agent 记忆。
- 保留所有 `running` 和 `stop_timeout` 可以避免误删仍需处理的进程和清理失败证据。

影响（Impact）:

- `process-manager` 的 manager config、状态模型、list 输出和文档规则会变化。
- `complex-coding-harness` 需要补充证据保留规则，避免被 prune 的 `runDir` 成为唯一验证证据。

可逆性（Reversibility）:

- 代码可回退；已经自动删除的旧 runDir 不可恢复，因此实现前必须通过路径安全和测试。

变更条件（Change conditions）:

- 如果实现发现默认删除 runDir 风险过大，可改为 `deleteRunDirs = false` 并重新请求用户确认。
- 如果用户要求长期保留更多历史，可调整默认 `maxInactive` 或支持用户配置。

方案变更触发条件（Reapproval triggers）:

- 需要引入第三方依赖。
- 需要支持非 Windows 平台。
- 需要删除 running 或 stop_timeout。
- 需要改变 service config 结构或启动协议。
- 需要默认提交 runtime artifact。

## 影响面矩阵（Impact Matrix）

| 影响对象（Surface） | 是否涉及（Involved） | 文件/模块（Files/modules） | 风险（Risk） | 验证方式（Validation） | 文档更新（Docs） |
| --- | --- | --- | --- | --- | --- |
| API | yes | `/processes` 可选 history 查询、可选 prune 摘要 | 客户端兼容性 | `pm_list` smoke 和 API 返回结构检查 | 是 |
| 数据结构（Data model） | yes | `ManagerConfig`、`processes.json` 裁剪规则 | 误删或状态丢失 | 合成状态和真实生命周期测试 | 是 |
| 前端交互（Frontend interaction） | no | 无 | 无 | 不适用 | 否 |
| 配置/环境（Config/environment） | yes | `manager-config.json`、`pm_init.py` | 旧配置兼容 | 旧配置加载测试 | 是 |
| 兼容性（Compatibility） | yes | `pm_list.py` 默认输出变化 | 依赖完整 processes 的调用方需加 `--history` | eval 和脚本 smoke | 是 |
| 测试（Tests） | yes | 临时 workspace、示例服务、合成状态 | 覆盖不足 | py_compile、JSON、lifecycle smoke | 是 |
| 文档（Documentation） | yes | 两个 skill 的 SKILL/workflow/template/eval | 规则遗漏 | quick_validate、rg 检查 | 是 |

## 实施计划（Implementation Plan）

### 阶段 1（Stage 1）：历史配置和裁剪核心

目标（Goal）:

- 在 `process-manager` 内建立可复用、可测试的 history 配置和 prune 核心逻辑。

做法（How）:

- 在 `pm_common.py` 的 `ManagerConfig` 增加 `history_max_inactive` 和 `history_delete_run_dirs`。
- 在 `create_default_manager_config()` 和 `templates/manager-config.json` 写入：

```json
"history": {
  "maxInactive": 20,
  "deleteRunDirs": true
}
```

- 旧配置没有 `history` 时按默认值兼容，不要求用户手动迁移。
- 在 manager 侧实现内部 prune 函数：
  - 先刷新状态。
  - 保护 `running` 和 `stop_timeout`。
  - inactive 按时间从新到旧保留最近 `maxInactive` 条。
  - 其余 inactive 从 `processes` 删除。
  - 若 `deleteRunDirs` 为 true，同步删除对应精确 `runDir`。

原因（Why）:

- 配置入口统一后，自动裁剪、手动裁剪、文档模板可以共享同一策略。
- 旧配置兼容可以避免已初始化项目被破坏。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/process-manager/scripts/pm_common.py`
  - `skills/process-manager/scripts/manager_server.py`
  - `skills/process-manager/templates/manager-config.json`
- API/配置（APIs/configs）:
  - `history.maxInactive`
  - `history.deleteRunDirs`
- 测试/文档（Tests/docs）:
  - JSON 模板解析
  - 旧 config 兼容检查

参考来源（References）:

- 当前 `ManagerConfig` 和端口重试配置模式。
- 当前 `load_processes()` 和 `save_processes()` 状态文件模式。

验证（Validation）:

- `python -m py_compile skills/process-manager/scripts/*.py`
- 构造临时 config，确认缺省 history 加载为 `maxInactive=20`、`deleteRunDirs=true`。
- 构造超过 20 条 inactive 的 synthetic state，确认只移除最旧 inactive。

风险和回滚（Risks and rollback）:

- 风险：路径删除过宽。
- 控制：只删除 `runs/<service>/<processId>` 精确目录，且目录必须位于 `config.runs_dir` 下。
- 回滚：禁用 prune 调用或将 `history.deleteRunDirs` 改为 false。

阶段契约（Stage Contract）:

- 范围（Scope）: history 配置、prune 函数、模板。
- 允许修改（Allowed changes）: process-manager 脚本和模板。
- 禁止修改（Forbidden changes）: service launcher 协议、readiness 协议、非 Windows 支持。
- 进入条件（Entry checks）: 用户批准方案；Git 切到 `harness/feature` 并同步主分支。
- 退出条件（Exit checks）: 核心裁剪逻辑和配置兼容测试通过。
- 必需验证（Required validation）: py_compile、合成状态 prune 测试、模板 JSON 解析。
- 是否预期提交（Commit expected）: 是，若用户批准阶段提交。

### 阶段 2（Stage 2）：`pm_list` 默认视图和手动清理脚本

目标（Goal）:

- 让日常 list 输出聚焦当前态，并提供显式历史查看和手动清理入口。

做法（How）:

- 修改 manager `/processes`：
  - 默认返回 `active`、`running` 和 `pruned` 摘要。
  - 查询 `?history=1` 时额外返回保留后的 `processes`。
- 修改 `pm_list.py`：
  - 默认不显示完整历史。
  - 新增 `--history`，请求完整保留历史。
- 新增或实现 `pm_prune.py`：
  - 默认 `--dry-run`。
  - `--apply` 才实际执行手动 prune。
  - 支持 `--max-inactive` 临时覆盖。
  - 支持 `--keep-runs` 临时不删 runDir。

原因（Why）:

- `pm_list` 是用户和 agent 最常用的入口，默认输出必须清爽。
- 手动 prune 方便用户在 manager 已运行时主动检查清理效果。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/process-manager/scripts/manager_server.py`
  - `skills/process-manager/scripts/pm_list.py`
  - `skills/process-manager/scripts/pm_prune.py`
- API/配置（APIs/configs）:
  - `GET /processes?history=1`
  - 可选 `POST /processes/prune` 或内部脚本调用现有 API，具体实现阶段按最小改动决定。
- 测试/文档（Tests/docs）:
  - `pm_list` 默认输出和 `--history` 输出。

参考来源（References）:

- 当前 `pm_status.py` 和 `pm_list.py` 的 argparse + `http_request` 模式。

验证（Validation）:

- 启动临时 manager 后，连续启动/停止短生命周期服务超过上限。
- 验证默认 `pm_list.py` 不包含完整 `processes`。
- 验证 `pm_list.py --history` 只包含保留历史。
- 验证 `pm_prune.py --dry-run` 不改 state，`--apply` 才执行。

风险和回滚（Risks and rollback）:

- 风险：脚本输出结构变化影响旧使用习惯。
- 控制：`--history` 提供完整历史入口；文档明确变更。
- 回滚：恢复默认返回 `processes`，保留 prune 核心。

阶段契约（Stage Contract）:

- 范围（Scope）: list/prune CLI 和 manager API。
- 允许修改（Allowed changes）: `pm_list.py`、新增 `pm_prune.py`、manager route。
- 禁止修改（Forbidden changes）: `pm_start` 启动语义、`pm_stop` 停止语义。
- 进入条件（Entry checks）: 阶段 1 通过。
- 退出条件（Exit checks）: 默认视图、历史视图和手动清理验证通过。
- 必需验证（Required validation）: CLI smoke、JSON 输出检查、无 running 误删。
- 是否预期提交（Commit expected）: 是，若用户批准阶段提交。

### 阶段 3（Stage 3）：process-manager 文档、示例和 eval

目标（Goal）:

- 把 history/prune 行为固化到 skill 规则中，避免后续 agent 不知道 `pm_list` 默认行为和自动清理策略。

做法（How）:

- 更新 `skills/process-manager/SKILL.md`：
  - `pm_list.py` 描述改为默认列出 current/running。
  - 增加 `pm_prune.py`。
  - 增加历史保留硬边界摘要。
- 更新 `skills/process-manager/references/workflow.md`：
  - 新增 `Process History` 章节。
  - 明确默认保留策略、inactive 定义、protected status、runDir 删除安全规则。
  - 明确 `pm_list --history` 用法。
- 更新模板和示例 JSON。
- 更新 eval prompt，覆盖：
  - 默认 list 不展示历史。
  - 超过上限裁剪 inactive。
  - running/stop_timeout 不自动删除。
  - runDir 删除必须路径安全。

原因（Why）:

- skill 的核心价值是让新会话的 agent 读到可靠规则；只改代码不改规则会导致上下文恢复后再次误用。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/process-manager/SKILL.md`
  - `skills/process-manager/references/workflow.md`
  - `skills/process-manager/templates/manager-config.json`
  - `evals/process-manager/prompts.jsonl`
- API/配置（APIs/configs）:
  - 无新增外部接口。
- 测试/文档（Tests/docs）:
  - `quick_validate.py skills/process-manager`
  - JSON/JSONL 解析。

参考来源（References）:

- `skill-creator` 对 skill 简洁和 progressive disclosure 的要求。

验证（Validation）:

- skill quick validate。
- `rg` 检查关键规则写入。
- JSON/JSONL 解析。

风险和回滚（Risks and rollback）:

- 风险：`SKILL.md` 过长。
- 控制：把细节放入 `references/workflow.md`，`SKILL.md` 只保留核心规则和脚本导航。

阶段契约（Stage Contract）:

- 范围（Scope）: process-manager skill 文档、模板、eval。
- 允许修改（Allowed changes）: 规则和验证样例。
- 禁止修改（Forbidden changes）: 无关 README 或额外说明文档。
- 进入条件（Entry checks）: 阶段 1、2 通过。
- 退出条件（Exit checks）: skill 校验和 eval 解析通过。
- 必需验证（Required validation）: quick_validate、JSONL parse、关键规则检索。
- 是否预期提交（Commit expected）: 是，若用户批准阶段提交。

### 阶段 4（Stage 4）：complex-coding-harness 联动更新

目标（Goal）:

- 让复杂长任务在使用 `process-manager` 时知道历史会被裁剪，必须把关键验证证据写入任务记录，而不是依赖旧 runDir 永久存在。

做法（How）:

- 更新 `skills/complex-coding-harness/references/workflow.md`：
  - 在长期进程管理规则中补充 `pm_list` 默认只展示当前态。
  - 需要历史时必须显式使用 `pm_list.py --history`。
  - 长任务的验证证据不能只引用可能被 prune 的旧 `runDir`；关键日志摘要、截图、trace、processKey 和结果必须写入 `execution-plan.md` 或任务 artifacts。
  - 每阶段退出前先采集必要日志证据，再允许服务停止和历史清理自然发生。
- 更新 `skills/complex-coding-harness/templates/execution-plan.md`：
  - `Process Manager Gate` 增加“证据保留位置”和“是否需要历史视图”字段。
  - `Stage Exit Gate` 增加“关键日志已沉淀”检查描述。
- 更新 eval prompt：
  - 覆盖上下文恢复后使用 `pm_list --history` 的场景。
  - 覆盖最终交付不能只引用被 prune 的 runDir 的场景。

原因（Why）:

- `complex-coding-harness` 是长任务稳定执行的上层流程。`process-manager` 的清理策略改变后，上层必须约束证据保存，否则最终交付可能引用已被自动删除的日志目录。

位置（Where）:

- 文件/模块（Files/modules）:
  - `skills/complex-coding-harness/references/workflow.md`
  - `skills/complex-coding-harness/templates/execution-plan.md`
  - `evals/complex-coding-harness/prompts.jsonl`
- API/配置（APIs/configs）:
  - 无。
- 测试/文档（Tests/docs）:
  - `quick_validate.py skills/complex-coding-harness`
  - JSONL 解析。

参考来源（References）:

- 当前 `complex-coding-harness` 的 Process Manager Gate、Stage Entry/Exit Gate 和 Resume Summary 规则。

验证（Validation）:

- skill quick validate。
- 模板关键字段检索。
- eval JSONL 解析。

风险和回滚（Risks and rollback）:

- 风险：complex-coding-harness 规则变繁琐。
- 控制：只补充与证据保留直接相关的规则，不扩大长期进程管理章节。

阶段契约（Stage Contract）:

- 范围（Scope）: complex-coding-harness 规则、模板、eval。
- 允许修改（Allowed changes）: 长期进程门禁和证据记录字段。
- 禁止修改（Forbidden changes）: 任务分级、Git 分支策略、提交规范。
- 进入条件（Entry checks）: process-manager 行为已实现并验证。
- 退出条件（Exit checks）: quick_validate、JSONL parse、规则检索通过。
- 必需验证（Required validation）: skill 校验和模板检索。
- 是否预期提交（Commit expected）: 是，若用户批准阶段提交。

### 阶段 5（Stage 5）：端到端验证和收口

目标（Goal）:

- 用真实临时服务验证历史裁剪不会破坏长期进程管理主流程。

做法（How）:

- 创建临时 workspace，不提交临时运行产物。
- 使用 `pm_init.py` 初始化 config，确认默认 history 字段。
- 启动 manager。
- 用简单 Python worker 或 HTTP 服务反复启动、ready、stop 超过 `maxInactive`。
- 验证：
  - running 服务仍可查。
  - inactive 超过上限后被裁剪。
  - 对应 runDir 被删除。
  - `pm_list.py` 默认输出不刷历史。
  - `pm_list.py --history` 输出保留历史。
  - manager 停止后无端口和进程残留。

原因（Why）:

- 该变更涉及进程状态和文件删除，必须做真实生命周期验证，不能只靠静态检查。

位置（Where）:

- 文件/模块（Files/modules）:
  - 临时 workspace。
  - `skills/process-manager/scripts/*`
- API/配置（APIs/configs）:
  - `.harness/process-manager/config.json`
  - `.harness/process-manager/processes.json`
- 测试/文档（Tests/docs）:
  - 临时验证脚本或命令记录写入执行计划。

参考来源（References）:

- 现有 process-manager lifecycle smoke 验证方式。

验证（Validation）:

- py_compile。
- quick_validate 两个 skill。
- JSON/JSONL 解析。
- 端到端 lifecycle smoke。
- `git diff --check`。

风险和回滚（Risks and rollback）:

- 风险：验证过程中 manager 或服务残留。
- 控制：使用 `pm_stop.py` 和 `stop_manager.ps1` 清理；若失败，记录 PID 并请求确认后处理。

阶段契约（Stage Contract）:

- 范围（Scope）: 验证和最终记录。
- 允许修改（Allowed changes）: harness 执行记录、changelog。
- 禁止修改（Forbidden changes）: 无关功能改动。
- 进入条件（Entry checks）: 阶段 1-4 通过。
- 退出条件（Exit checks）: 验证通过、记录完整、无残留服务。
- 必需验证（Required validation）: 端到端 smoke 和静态检查。
- 是否预期提交（Commit expected）: 是，若用户批准阶段提交。

## 环境（Environment）

Workspace 环境来源（Workspace environment source）:

- `.harness/environment.md`

本任务使用（This task uses）:

- Python 标准库。
- PowerShell。
- Git。
- `skill-creator` 的 `quick_validate.py`。

临时覆盖（Temporary overrides）:

- 无。

## Git 上下文（Git Context）

主分支（Main branch）:

- main

任务类型（Task type）:

- feature

工作分支（Working branch）:

- harness/feature

分支动作（Branch action）:

- 当前仅落盘方案；实现前必须检查工作区并切换或复用 `harness/feature`。

同步来源（Sync source）:

- origin/main 或本地 main，按实现前实际网络和远程状态确认。

最近同步（Last sync）:

- pending

分支占用（Branch occupancy）:

- `git log <main>..HEAD`: pending
- `git diff <main>...HEAD --name-only`: pending
- 现有提交属于本任务（Existing commits belong to this task）: pending

提交策略（Commit policy）:

- 用户确认方案并授权后，每阶段完成 review、验证和记录更新后提交。
- 使用 `git commit -F .harness/tasks/2026-06-12/feature/process-manager-history-retention/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。

分支收口（Branch closure）:

- 已合回主分支（Merged to main branch）: no
- 未合回时代码停留在（If not merged, code remains on）: harness/feature
- 合并前需要用户确认（User confirmation needed before merge）: yes

分支安全（Branch safety）:

- 切换前已检查工作区：pending
- 不自动 stash：yes
- 不自动 rebase：yes
- 不自动 reset：yes

热修复插入（Hotfix interruption）:

- 从 `harness/feature` 切换到 `harness/fix` 前，先询问是否要把 feature 合并进主分支：yes
- 决策：pending

未解决问题（Open issues）:

- 普通 `git status` 触发 ownership 保护；实现和提交前继续使用一次性 `git -c safe.directory=E:/work/hl/videoForensic/AI/dev-skills ...`，或由用户另行确认写入全局配置。

## 工具（Tooling）

| 工具（Tool） | 用途（Purpose） | 阶段（Stage） | 状态（Status） | 风险（Risk） | 替代方案（Alternative） | 用户确认（User confirmation） |
| --- | --- | --- | --- | --- | --- | --- |
| Python | 脚本语法和生命周期 smoke | 1-5 | available | 当前环境差异 | 使用当前可用 Python | not required |
| PowerShell | manager bootstrap 和 Windows 命令 | 5 | available | sandbox/权限 | 请求授权执行必要命令 | if needed |
| Git | 分支、diff、提交 | all | ownership protected | 普通 git status 失败 | 使用一次性 safe.directory | not required |
| process-manager | 本任务自身验证对象 | 5 | available as local skill code | manager 启动可能占端口 | 使用端口重试 | if bootstrap needed |

## 长期进程管理（Process Manager Gate）

是否需要长期后台进程（Needs long-running processes）:

- yes，阶段 5 需要启动临时 manager 和临时服务做生命周期验证。

process-manager skill 是否存在（process-manager skill available）:

- yes，本仓库包含 `skills/process-manager`。

规则结论（Rule decision）:

- 实现阶段如果启动任何长期后台进程，必须使用 `process-manager` 自己的脚本管理。
- finite command，例如 py_compile、quick_validate、JSON 解析、git diff，不进入 `process-manager`。
- manager 离线时必须停止长期进程操作，请求用户手动启动 manager 或授权 bootstrap；不能退回 shell 后台启动。

需要托管的服务（Managed services）:

| 服务（Service） | 类型（Type） | 阶段（Stage） | service config | readiness | processKey | 日志/证据（Logs/evidence） | 清理状态（Cleanup） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| temp-python-worker | worker/http | 5 | 临时 workspace | process/http/log | pending | pending | pending |

禁止 shell 后台启动确认（No shell background start）:

- pending，实施阶段每次启动长期进程前复查。

证据保留要求（Evidence retention）:

- 因新策略会自动删除旧 inactive 的 runDir，最终交付需要保留的日志必须摘录进 `execution-plan.md` 或复制到任务 artifacts。
- 不把旧 `runs/<service>/<processId>` 当作长期稳定证据来源。

每阶段复查要求（Per-stage reread requirement）:

- Stage Entry Gate 前必须复查本节。
- 启动、验证、调试长期进程前必须复查本节。
- 上下文压缩或中断恢复后必须复查本节和 `Resume Summary`。

## 验证（Validation）

必需验证（Required）:

- `python -m py_compile` 覆盖 process-manager Python 脚本。
- `quick_validate.py skills/process-manager`。
- `quick_validate.py skills/complex-coding-harness`。
- JSON/JSONL 解析覆盖模板、示例和 eval。
- 临时 workspace lifecycle smoke，覆盖 start、ready/status、stop、list、history prune、runDir 删除。
- `git diff --check`。

已执行（Executed）:

- 命令/工具（Command/tool）: pending
- 结果（Result）: pending
- 证据（Evidence）: pending
- 覆盖范围（Covers）: pending
- 未覆盖（Not covered）: pending

验证证据表（Validation Evidence）:

| 阶段（Stage） | 命令/工具（Command/tool） | 结果（Result） | 覆盖内容（Covers） | 未覆盖（Not covered） | 证据/日志（Evidence/log） | 处理（Action） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | py_compile / synthetic prune | pending | 配置和 prune 核心 | 真实 lifecycle | pending | pending |
| 2 | pm_list / pm_prune smoke | pending | CLI 输出和手动清理 | 文档规则 | pending | pending |
| 3 | quick_validate / JSONL parse | pending | process-manager skill | 真实 harness 使用 | pending | pending |
| 4 | quick_validate / JSONL parse | pending | complex-coding-harness 联动规则 | 真实长任务 | pending | pending |
| 5 | lifecycle smoke | pending | 端到端状态和 runDir 删除 | 非 Windows | pending | pending |

可选验证（Optional）:

- 用多个 service 名称混合启动，确认全局 inactive 上限按所有 service 总数计算。

产物（Artifacts）:

- 截图（Screenshot）: 不需要。
- 日志（Log）: lifecycle smoke 关键输出摘录到本文件。
- Trace: 不需要。
- 报告（Report）: 不需要。

未覆盖（Not covered）:

- 非 Windows 平台。
- 真实业务项目长期运行多天后的历史增长。

无法执行时（If unable to run）:

- 必须记录失败原因、替代静态验证和剩余风险，不能声称通过。

## 文档（Documentation）

必需更新（Required updates）:

- `skills/process-manager/SKILL.md`
- `skills/process-manager/references/workflow.md`
- `skills/process-manager/templates/manager-config.json`
- `evals/process-manager/prompts.jsonl`
- `skills/complex-coding-harness/references/workflow.md`
- `skills/complex-coding-harness/templates/execution-plan.md`
- `evals/complex-coding-harness/prompts.jsonl`

Changelog 计划（Changelog plan）:

- 如仓库已有 `CHANGELOG.md`，实施完成后记录历史裁剪、`pm_list` 默认视图、`runs` 同步删除和 complex-coding-harness 证据保留规则。

## 问题和覆盖项（Questions And Overrides）

| ID | 是否阻塞（Blocking） | 状态（Status） | 问题（Question） | 决策（Decision） | 应用位置（Applied to） |
| --- | --- | --- | --- | --- | --- |
| D-001 | no | decided | inactive 裁剪是否同步删除 runDir | 是，默认同步删除，但只允许删除精确 runDir | process-manager history |
| D-002 | no | decided | complex-coding-harness 是否需要更新 | 是，轻量更新证据保留和 `pm_list --history` 规则 | complex-coding-harness gate |

## 就绪门禁（Readiness Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 目标和验收清楚（Goal and acceptance clear） | pass | 本文件 Problem 和 Acceptance |
| 上下文已收集（Context collected） | pass | 已读取 process-manager 和 complex-coding-harness 相关文件 |
| 候选方案已比较（Options compared） | pass | 方案 A/B/C |
| 决策已记录（Decision recorded） | pass | 选择方案 C |
| 实施阶段已细化（Implementation stages detailed） | pass | 阶段 1-5 |
| 环境已确认（Environment confirmed） | pass | `.harness/environment.md` |
| Git 上下文已确认（Git context confirmed） | partial | 主分支和目标分支已记录；实现前需检查并切换 |
| 工具已确认（Tooling confirmed） | pass | Python、PowerShell、Git |
| 验证已确认（Validation confirmed） | pass | Validation 章节 |
| 最终交付证据已规划（Final delivery evidence planned） | pass | 证据表和 artifacts 规则 |
| 文档更新已确认（Documentation updates confirmed） | pass | Documentation 章节 |
| 风险已识别（Risks identified） | pass | 删除安全、证据保留、兼容性 |
| 阻塞问题已关闭（Blocking questions closed） | pass | 无 blocking |

## 方案质量门禁（Plan Quality Gate）

| 检查项（Check） | 状态（Status） | 证据（Evidence） |
| --- | --- | --- |
| 关键判断有证据等级（Evidence levels assigned） | pass | Evidence levels 表 |
| 影响面矩阵完整（Impact matrix complete） | pass | Impact Matrix |
| 候选方案比较充分（Options compared enough） | pass | 三个候选方案 |
| 每阶段可独立验证（Stages independently verifiable） | pass | 每阶段都有 Required validation |
| 方案变更触发条件清楚（Reapproval triggers clear） | pass | Decision 章节 |
| 用户批准摘要可记录（Approval summary ready） | pass | Plan Approval 章节 |

就绪结论（Readiness result）:

- `ready_for_approval`

## 方案批准（Plan Approval）

状态（Status）:

- `approved`

批准记录（Approval record）:

- 2026-06-12 用户确认：“确认方案，执行吧”

批准摘要（Approval summary）:

- 批准范围（Approved scope）: 按本计划阶段 1-5 实现 process-manager 历史保留、runDir 同步清理、pm_list/pm_prune、相关 skill 规则和验证收口。
- 阶段提交授权（Stage commit authorization）: 每阶段 review、验证和记录更新后提交。
- 工具/MCP 授权（Tool/MCP authorization）: 允许使用 Python、PowerShell、Git 和 process-manager 自身脚本；需要启动长期进程时按 Process Manager Gate 执行。
- 文档更新授权（Documentation authorization）: 允许更新 process-manager、complex-coding-harness、eval、模板和 changelog。

提交策略（Commit policy）:

- `stage_commits_authorized`

## 实施进度（Implementation Progress）

| 阶段（Stage） | 状态（Status） | 摘要（Summary） | 验证（Validation） | 证据（Evidence） | 下一步（Next action） |
| --- | --- | --- | --- | --- | --- |
| planning | completed | 已完成历史保留和联动规则方案 | 文档结构待校验 | 本文件 | 等待用户确认方案 |
| 1 | completed | 已实现 history 默认配置、旧配置兼容、inactive 裁剪核心和精确 runDir 删除 | py_compile、模板 JSON、合成状态 prune 通过 | `stage1 synthetic prune ok` | 阶段 2 |
| 2 | completed | 已实现 `pm_list --history`、默认轻量视图和 `pm_prune.py` dry-run/apply | py_compile、help、合成 list/prune 行为通过 | `stage2 list prune behavior ok` | 阶段 3 |
| 3 | completed | 已更新 process-manager SKILL、workflow 和 eval，固化历史保留与 pm_prune 规则 | quick_validate、JSONL 解析、关键规则检索通过 | `Skill is valid!`、fixtures 9 条 | 阶段 4 |
| 4 | completed | 已更新 complex-coding-harness 的历史视图、证据保留和模板门禁规则 | quick_validate、JSONL 解析、模板表格检查通过 | complex prompts 21 条，表格列数 10/10/10 | 阶段 5 |
| 5 | pending | 端到端验证和收口 | pending | pending | 阶段 4 后开始 |

## 阶段进入门禁（Stage Entry Gate）

| 阶段（Stage） | 当前分支/工作区（Git/worktree） | 上阶段遗留（Previous findings） | 环境和工具（Environment/tooling） | 长期进程门禁（Process manager gate） | 范围匹配（Scope match） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | pass | none | pass | not-applicable | pass | pass |
| 2 | pass | none | pass | not-applicable | pass | pass |
| 3 | pass | none | pass | not-applicable | pass | pass |
| 4 | pass | none | pass | not-applicable | pass | pass |
| 5 | pending | pending | pending | pending | pending | pending |

## 阶段退出门禁（Stage Exit Gate）

| 阶段（Stage） | 目标完成（Goal done） | Review 完成（Review done） | 验证完成（Validation done） | 长期进程清理和证据（Process cleanup/evidence） | 记录更新（Records updated） | 提交记录（Commit recorded） | 结论（Result） |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | pass | pass | pass | not-applicable | pass | pending | pass |
| 2 | pass | pass | pass | not-applicable | pass | pending | pass |
| 3 | pass | pass | pass | not-applicable | pass | pending | pass |
| 4 | pass | pass | pass | not-applicable | pass | pending | pass |
| 5 | pending | pending | pending | pending | pending | pending | pending |

## 代码审查（Code Review）

| 阶段（Stage） | 问题（Finding） | 严重程度（Severity） | 处理（Resolution） |
| --- | --- | --- | --- |
| planning | 方案确认：`complex-coding-harness` 需要轻量更新证据保留规则 | follow-up | 已纳入阶段 4 |
| 1 | `_prune_state(dry_run=True)` 原实现会在异常 state 时修改内存状态 | minor | 已修复为 dry-run 不修改 state |
| 2 | `pm_prune` dry-run 如果先刷新状态会写入 `process.json` | minor | 已改为 dry-run 不刷新、不保存，仅预估裁剪结果 |

## 恢复摘要（Resume Summary）

- 当前阶段（Current stage）: 阶段 4 completed，准备提交。
- 已完成（Completed）: 已实现 process-manager 行为和文档；已更新 complex-coding-harness 证据保留联动规则。
- 最新 commit（Latest commit）: `61a2147` 阶段 3。
- 下一步（Next action）: 提交阶段 4，然后进入阶段 5 端到端验证。
- 长期进程规则（Process manager rule）: 阶段 5 需要长期进程，必须使用 process-manager；本任务新规则要求关键证据不能只依赖可能被 prune 的 runDir。
- 未覆盖/风险（Not covered/risks）: 实现前尚未验证路径删除；当前 Git 普通命令有 ownership 保护。

## 提交记录（Commit Log）

提交信息方式（Commit message method）:

- 使用 `git commit -F .harness/tasks/2026-06-12/feature/process-manager-history-retention/tmp/commit-message.txt`。
- 禁止用多个 `-m` 分别传入 bullet。
- 提交前检查标题后正好一个空行，bullet 之间没有空行。

| 阶段（Stage） | 仓库（Repository） | Commit | Message | Changelog |
| --- | --- | --- | --- | --- |
| planning | dev-skills | not committed | not authorized | pending |
| 1 | dev-skills | `9960512` | `feat(process-manager): 增加历史裁剪核心` | pending |
| 2 | dev-skills | `0e6afe4` | `feat(process-manager): 增加历史列表和裁剪命令` | pending |
| 3 | dev-skills | `61a2147` | `docs(process-manager): 记录历史保留规则` | pending |
