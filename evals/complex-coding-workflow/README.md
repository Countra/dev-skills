# Compact Coding Workflow Eval

`run_evals.py` 只执行确定性本地检查：验证六个生产脚本边界，并通过公共 CLI 走完四文件 managed 生命周期。

它不访问网络、不创建 Agent、不运行目标应用、不调用 `codex exec`，也不保存 eval JSON 或上传 artifact。
