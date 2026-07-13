# Skill Evaluation Workflow

只在需要设计评测、转换既有 fixture、解释结果或运行 live 矩阵时读取本文。公共脚本均为有限命令，不启动后台服务，也不会自动修改被评估 skill。

## 目录

1. [定义决策问题](#1-定义决策问题)
2. [盘点现有证据](#2-盘点现有证据)
3. [设计 case 组合](#3-设计-case-组合)
4. [选择 baseline](#4-选择-baseline)
5. [校验与预览](#5-校验与预览)
6. [运行](#6-运行)
7. [评分与报告](#7-评分与报告)
8. [迭代与停止](#8-迭代与停止)

## 1. 定义决策问题

先写一句可证伪的问题，例如：

- 新 description 是否提高目标请求的触发率，同时不增加 near miss 误触发？
- candidate 是否比无 skill baseline 更稳定地产生规定 artifact？
- 重构是否降低 token 使用，且没有降低行为通过率？

不要使用“整体更好”作为唯一目标。分别定义 trigger、behavior、cost 和 regression 证据；没有足够样本时保留 `low_information`。

## 2. 盘点现有证据

需要仓库级全貌时运行：

```text
python -u -X utf8 -B scripts/se_inventory.py --root <repo> --pretty
```

inventory 是只读扫描，只报告 skill metadata、公共脚本、单元测试、eval 目录和 CI 引用。现有 eval 命令保持原样；只有需要统一 paired run 或报告时，才新增 suite 作为并行入口。

转换既有 eval 时保留：

1. 原 prompt/fixture 的意图与原命令。
2. 原先可执行的机械断言。
3. 原始 pass/fail 证据，避免先按新 runner 重写历史结论。

## 3. 设计 case 组合

Trigger case 至少覆盖：

- 明确正例：用户直接请求该 skill 的核心能力。
- 自然正例：不点名 skill，但语义应触发。
- near miss：词汇相近但应由普通工具或另一个 skill 处理。
- 明确负例：不属于能力边界的任务。

Behavior case 使用相同 prompt、inputs、model、sandbox、timeout 和 repetition 比较 candidate/baseline。只有 skill snapshot 可以不同。机械 assertion 与 grader oracle 不得进入 prompt 或 agent workspace。

Split 用途：

- `train`：编写 skill 时可反复查看和调试。
- `validation`：比较候选修改并做阶段决策。
- `holdout`：定稿前才运行，避免按答案调整 skill。

不要靠大量同义改写替代真实任务多样性。重复次数用于估计随机性，不用于扩充 case 覆盖。

## 4. 选择 baseline

- `none`：回答“有这个 skill 是否优于没有”。
- `snapshot`：回答“新版本是否优于明确的旧版本目录”。

baseline 必须是独立目录，不能与 candidate 指向同一路径。不要在运行中修改 snapshot；任何 source hash 变化都必须重新 plan。

## 5. 校验与预览

```text
python -u -X utf8 -B scripts/se_validate.py --suite <suite.json> --pretty
python -u -X utf8 -B scripts/se_plan.py --suite <suite.json> --output <preview.json> --pretty
```

预览后检查：

1. candidate/baseline source identity 是否正确。
2. trigger 只运行 candidate，behavior 是否成对。
3. case repetition 与最大 agent run 数是否一致。
4. 配对顺序是否按 repetition 交替，声明并发与实际串行顺序是否符合预期。
5. fingerprint 是否已记录；它同时绑定 suite、candidate/baseline 与当前 lab 实现树，live 授权只对该值有效。

## 6. 运行

离线 fake suite：

```text
python -u -X utf8 -B scripts/se_run.py --suite <suite.json> --work-root <run-root>
```

真实 Codex suite 必须先向用户展示 model、矩阵、调用上限、墙钟上限和 fingerprint。获得明确授权后才运行：

```text
python -u -X utf8 -B scripts/se_run.py --suite <suite.json> --work-root <run-root> --fingerprint <sha256> --authorize-live
```

不得自行把 timeout、unknown outcome 或写入失败重放为新尝试。先保留原 artifact，诊断是否属于 runner、权限、case 或 skill 问题；任何输入变化都重新 plan。

## 7. 评分与报告

```text
python -u -X utf8 -B scripts/se_grade.py --run <run.json> --output <grade.json>
python -u -X utf8 -B scripts/se_report.py --grade <grade.json> --json-output <report.json> --markdown-output <report.md>
```

先看确定性 failure taxonomy，再看 paired delta。报告必须同时说明：

- 每个 variant/mode 的 `n`、passed、pass rate 和 Wilson 区间。
- behavior pair 的 wins/losses/ties、排除原因和低信息标记。
- token 字段是否完整、duration 是否可用。
- fingerprint、model、adapter、CLI、sandbox、network 和权限配置。
- human/judge 是否存在，以及 judge 是 advisory 还是 calibrated decision。
- 每个 required gate 的 evidence 是否可用、实际值是否达到阈值。

两个结果都失败、全部 tie、样本过少或 provenance 不兼容时，不得宣称 candidate 提升。

## 8. 迭代与停止

一次只修改一个可解释变量，例如 description、工作流指令或脚本。修改后重新 validate/plan，并保留旧报告用于比较。

满足以下任一条件时停止并补证据，而不是继续扩大调用：

- case 定义或 oracle 仍有歧义。
- holdout 已被用于调参。
- candidate/baseline 运行条件不一致。
- 失败来自 runner capability 或权限，无法归因到 skill。
- 预算不足以产生有解释力的样本。
