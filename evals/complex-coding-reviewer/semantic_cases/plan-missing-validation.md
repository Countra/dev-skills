# Seeded Plan: Missing Verification

## Goal

为配置文件新增严格 schema 校验，非法字段必须返回稳定错误。

## Stage

修改 parser 和错误码，然后运行现有 happy-path 单测。完成后人工确认行为合理。

## Approval

计划声明所有验收已经闭合，可以进入实施。

## Seed Intent

该样本故意没有非法字段、未知字段和错误码断言，也没有可重复的验收命令。专业 plan-review 应报告验证无法证伪目标，
不能因为存在“运行单测”字样而通过。
