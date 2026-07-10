# 临时决策单（Pending Decisions）

请在 `USER INPUT` 区域内填写你的决定。你也可以不编辑文件，直接在会话中回复选项或自定义内容。

## D-001：<decision-title>

状态（Status）:
open

上下文（Context）:
<这里说明为什么该决策会阻塞任务>

证据（Evidence）:
- 

不确定性（Uncertainty）:
<哪些事实无法通过本地代码、官方资料或低成本探针确认>

已执行探针（Probe）:
- <检查动作、结果和限制>

选项（Options）:
- A（recommended）：<推荐选项>
- B：<备选项>
- C：<备选项>
- Custom：填写你的具体要求。

影响（Impact）:
<这里说明该决策会影响什么>

默认假设（Default assumption）:
<若用户选择推荐项，计划采用什么边界；不能安全默认时写 none>

重新批准影响（Reapproval effect）:
<该决定是否改变 scope、Stage DAG、必需验证、风险或授权>

合并目标（Merge target）:
`execution-plan.md` / `plan-contract.json` / 目标 artifact

>>> 📝 USER INPUT: D-001 >>>
Decision:

<<< END <<<

## 已关闭决策（Closed Decisions）

- 
