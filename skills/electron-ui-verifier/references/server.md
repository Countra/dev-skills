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
python skills/process-manager/scripts/pm_health.py
python skills/process-manager/scripts/pm_validate.py --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_start.py --service E:/work/hl/videoForensic/AI/dev-skills/.harness/process-manager/services/electron-ui-verifier.json
python skills/process-manager/scripts/pm_ready.py --service electron-ui-verifier
python skills/electron-ui-verifier/scripts/ev_health.py --workspace E:/work/hl/videoForensic/AI/dev-skills
```

`ev_server.py` 绑定成功后会输出：

```text
EV_READY http://127.0.0.1:<port>/health
```

process-manager service 使用 log readiness，因此端口重试后也能识别真实 health URL。

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

如果要把本次 report 沉淀到知识库，显式使用：

```powershell
python skills/electron-ui-verifier/scripts/ev_workflow.py --workspace E:/work/hl/videoForensic/AI/dev-skills --session videoForensic --workflow E:/work/task/open-case.workflow.json --learn --learn-app-id videoForensic --learn-notes "打开案件流程复验"
```

server 会先生成正常 report，再把知识学习摘要写入 `report.json` 的 `knowledge` 字段。`--learn` 只写基础候选知识；如需 action/workflow 资产，显式加 `--learn-assets`。学习失败不会把 UI 验证结果改成失败，但必须在最终说明里记录。

## 重要边界

- server 进程退出后 session 失效，必须重新 attach。
- 同名 session 默认复用；需要强制重新 attach 时用 `ev_attach.py --no-reuse`。
- 远程 CDP 必须显式批准并传 `--allow-remote-cdp`。
- `ev_report.py` 和 `ev_artifact.py` 只能读取 `.harness/electron-ui-verifier/` 下的运行产物。
- 知识库默认不自动写入；只有 `ev_learn.py`、`ev_action.py --learn` 或 `ev_workflow.py --learn` 会写入基础知识；只有 `--include-assets` 或 `--learn-assets` 会写 action/workflow 资产。
