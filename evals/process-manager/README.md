# process-manager executable eval

运行：

```text
python -X utf8 -B evals/process-manager/run_evals.py --work-dir <可写目录>
```

评测同时验证：

- agent fixtures 使用 explicit context、统一 ensure、session lease/finally close、current schema、按需 doctor 与 owner-empty 证据；
- 14 个公共 facade 的 help 可执行且不暴露平台/backend 选择；
- current service config 通过真实 `pm_validate.py`；
- 旧 `argv/window` schema 被稳定拒绝；
- 初始化后只读 status 返回 `absent` 与 `recommendedAction=ensure`，统一 `ensure` 负责幂等收敛；
- `pm_health.py`、`pm_shutdown.py` 和 status-then-start 不属于 current public contract；
- templates/examples 只有 `direct` 与 `script`，没有旧字段。

该 eval 不启动长期进程。真实进程树、graceful-force、probe、rotation、crash 与 cleanup 由 `skills/process-manager/tests/run_platform_smoke.py` 验证。
