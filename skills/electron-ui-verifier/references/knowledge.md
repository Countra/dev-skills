# Canonical Knowledge

只在查询、组合、reset、pending 审核或批准资产时读取本文件。

## 存储模型

- `knowledge/canonical/*.json` 是 approved truth，assetId 由内容摘要生成。
- `knowledge/manifest.json` 是 durable commit 与 canonical 摘要。
- `knowledge/derived/index.sqlite3` 是可删除、可重建的检索索引，使用 rollback journal，不使用 WAL。
- 旧布局不读取、不导入、不转换；retired 目录不参与 current 查询。

批准顺序固定为 canonical 原子提交、derived 单事务更新、sealed decision。derived 损坏时隔离旧文件并从 canonical 重建。

## 检索

```powershell
python <skill>/scripts/ev_knowledge.py --workspace <absolute-workspace> search --app-id <app> --query <goal>
```

检索通道包括 normalized exact goal、alias、FTS5 BM25、Latin token、CJK bigram/trigram，并用 RRF 融合。先执行 app/version/screen/preState/risk 硬过滤，再评分；默认最多返回 3 条。

结果：

- `reuse`：top score 和 margin 达标，可以进入现场复验。
- `abstain`：无 lexical candidate、无 compatible candidate、分数不足或候选过于接近。不要用 recent asset 补空。
- `--explain`：只在需要诊断召回时读取 channel rank、lexical、RRF、reliability 和 rejection reason。

完整目标失败时由 agent 显式提供子目标：

```powershell
python <skill>/scripts/ev_suggest.py --workspace <absolute-workspace> --app-id <app> --goal <goal> --subgoal <entry> --subgoal <action>
```

## 状态组合

`ev_knowledge.py compose` 只组合 action assets，并要求：

- 每项 retrieval 均为 `reuse`。
- 相邻 `postState == preState`，首项与当前 preState 一致。
- 风险不超过 `maxRisk`。
- 每个 `${name}` 都在 parameterSchema 声明并提供正确类型 binding。

组合输出保留占位符，不回显 binding value。任一状态边缺失、冲突或参数未绑定时 fail closed。

## 资产读取与执行

```powershell
python <skill>/scripts/ev_assets.py --workspace <absolute-workspace> list --app-id <app> --kind workflow
python <skill>/scripts/ev_assets.py --workspace <absolute-workspace> get --asset-id <id>
python <skill>/scripts/ev_workflow.py --workspace <absolute-workspace> --run-id <run-id> --workflow-id <id> --bindings <json>
```

`get` 从 canonical 文件读取并重新校验 content-addressed identity。执行时 parameter values 只在内存绑定，journal 只记录 placeholder 和 bound parameter name。

## Pending 与批准

finalize 只有在 run passed、存在 mutating path、postconditions 通过、证据完整且 workflow 可参数化时才创建 pending。

```powershell
python <skill>/scripts/ev_pending.py --workspace <absolute-workspace> --run-id <run-id>
python <skill>/scripts/ev_persist.py --workspace <absolute-workspace> approve --run-id <run-id> --fingerprint <exact> --note <reason>
```

批准前再次校验 report digest、evidence manifest、parameterSchema、risk confirmation 和 bundle fingerprint。decision 使用 exclusive create；重复同一批准幂等，其它决定冲突。

旧的 direct learn、promote 和 store facade 已删除，不存在兼容入口。
