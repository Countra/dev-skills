# Verifier Server

## 总体结构

Electron UI 验证由三部分组成：

- Electron GUI 应用：用户或普通终端命令启动，带 `--remote-debugging-port=<port>`。
- verifier server：常驻 Python HTTP 服务，维护 CDP session、事件缓冲、报告和 artifact。
- `ev_*` 脚本：封装 verifier server API，agent 只调用这些脚本。

Electron GUI 应用本体不要由 `process-manager` 托管。verifier server 是长期后台服务，必须由 `process-manager` 托管。

## 初始化

先初始化 verifier runtime：

```powershell
python E:/work/hl/videoForensic/AI/dev-skills/skills/electron-ui-verifier/scripts/ev_init.py --workspace E:/work/hl/videoForensic/AI/dev-skills --python F:/env/anaconda/python.exe
```

`--python` 必须是 verifier server 使用的 Python 解释器绝对路径。该路径会写入：

```text
.harness/electron-ui-verifier/environment.json
```

如果用户在会话里口头指定新的 Python 解释器，必须立即重新运行 `ev_init.py --python <abs-python>`，不能只把路径留在对话中。

`ev_init.py` 会先用目标 Python 执行依赖检查，检查通过后才写入 environment、config 和 process-manager service。必要依赖位于：

```text
skills/electron-ui-verifier/requirements.txt
```

也可以手工预检查：

```powershell
F:/env/anaconda/python.exe E:/work/hl/videoForensic/AI/dev-skills/skills/electron-ui-verifier/scripts/ev_check_env.py --requirements E:/work/hl/videoForensic/AI/dev-skills/skills/electron-ui-verifier/requirements.txt --json
```

如果输出 `ok: false`，必须停止当前验证任务，并把 `missing`、`pythonFailure` 和 `installCommand` 报告给用户。不得在依赖不完整时继续启动 verifier server 或执行 UI 验证。

初始化会生成：

```text
.harness/electron-ui-verifier/config.json
.harness/electron-ui-verifier/token
.harness/process-manager/services/electron-ui-verifier.json
```

这些都是本机运行产物，默认不提交。

## 内部文件目录边界

本 skill 自己生成和托管的内部文件固定写入：

```text
.harness/electron-ui-verifier/
```

该目录下包含：

```text
environment.json
config.json
token
server.json
sessions.json
reports/
pending/
workflows/
artifacts/
logs/
tmp/
knowledge/
```

不得为了单次任务、smoke、调试或知识库实验，在 `.harness` 下新建其它 electron-ui-verifier 内部目录，也不得把内部报告、截图、日志、临时文件或知识库写到项目根目录、`skills/` 目录、`.tmp/` 或其它 skill 的运行目录。

例外只有两类：

- verifier server 的进程托管 service 文件属于 process-manager，路径是 `.harness/process-manager/services/electron-ui-verifier.json`。
- 用户明确指定的输入或输出文件，例如外部 action/workflow JSON、导出的可分享 workflow，可以使用用户给定的绝对路径；这些不是本 skill 内部托管文件。

## 启动 server

按 process-manager 规则启动：

```powershell
# 仅在 process-manager config 不存在时初始化。
python skills/process-manager/scripts/pm_init.py --workspace E:/work/hl/videoForensic/AI/dev-skills
python skills/process-manager/scripts/pm_manager.py status --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json
# 仅在 manager_offline 时执行 start；不要判断 OS 或选择 backend。
python skills/process-manager/scripts/pm_manager.py start --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json
python skills/process-manager/scripts/pm_validate.py --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_start.py --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_ready.py --config E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/config.json --process-key <pm_start 返回的 processKey>
python skills/electron-ui-verifier/scripts/ev_health.py --workspace E:/work/hl/videoForensic/AI/dev-skills
```

`ev_server.py` 绑定成功后会输出：

```text
EV_READY http://127.0.0.1:<port>/health
```

process-manager service 使用有界增量 log readiness 和命名捕获组，因此 verifier 内部端口重试后也能识别真实 health URL。停止或重启 server 时必须保存 `cleanupVerified` 与 `stopResult.ownerEmpty` 证据。

## Session 流程

先探测 CDP targets：

```powershell
python skills/electron-ui-verifier/scripts/ev_probe.py --workspace E:/work/hl/videoForensic/AI/dev-skills --cdp http://127.0.0.1:9223
```

再 attach：

```powershell
python skills/electron-ui-verifier/scripts/ev_attach.py --workspace E:/work/hl/videoForensic/AI/dev-skills --name videoForensic --cdp http://127.0.0.1:9223 --target-index 0
```

后续复用 session：

```powershell
python skills/electron-ui-verifier/scripts/ev_snapshot.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --workflow E:/work/task/open-case.workflow.json
python skills/electron-ui-verifier/scripts/ev_report.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --latest
```

每次 `ev_workflow.py` 或 `ev_action.py` 执行后，返回值都会包含 `pendingPackage` 字段，指向本轮待确认审核包：

```text
.harness/electron-ui-verifier/pending/<session>/<timestamp>-<type>/
```

审核包内的 `workflow.proposed.json` 是清洗后的正确路径，`workflow-review.md` 是给用户确认的中文步骤，`detours.json` 只记录被排除的错误路径。最终回复必须引用 pending 包路径；用户确认后才引用正式 workflow 路径。

如果要把本次 report 沉淀到知识库，必须先获得用户确认，再显式使用：

```powershell
python skills/electron-ui-verifier/scripts/ev_persist.py --workspace E:/work/hl/videoForensic/AI/dev-skills approve --pending E:/work/hl/videoForensic/AI/dev-skills/.harness/electron-ui-verifier/pending/videoForensic/20260702-120000-workflow --decision "用户确认打开案件流程正确"
```

server 会先生成正常 report 和 pending 审核包。`approve` 会把清洗后的 workflow 晋级为正式 workflow，再写知识库；如需 action/workflow 资产，显式加 `--include-assets`。学习失败不会把 UI 验证结果改成失败，但必须在最终说明里记录。

## 重要边界

- server 进程退出后 session 失效，必须重新 attach。
- 同名 session 默认复用；需要强制重新 attach 时用 `ev_attach.py --no-reuse`。
- 远程 CDP 必须显式批准并传 `--allow-remote-cdp`。
- `ev_report.py` 和 `ev_artifact.py` 只能读取 `.harness/electron-ui-verifier/` 下的运行产物。
- 知识库默认不自动写入；普通 `ev_action.py` 和 `ev_workflow.py` 只生成 pending 审核包。只有用户确认后的 `ev_persist.py approve` 才写入基础知识；只有 `--include-assets` 会写 action/workflow 资产。
