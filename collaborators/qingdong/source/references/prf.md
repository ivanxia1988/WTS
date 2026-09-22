# PRF 子 Agent

PRF 子 Agent 读。PRF 是产生**待试词**的唯一来源；反思和救援只使用已有的词。待试词从高分简历的经历原文里抽，所以本步要读传入的详情文件。

## 输入

需求文件、本轮 `labels`、索引里的 `profile_path`（打开详情文件）、本轮搜索摘要（各路 query、新增/重复人数、各路新增可推荐人数、详情是否全部失败）、已有 `prf_decision`、已完成轮数。最大轮次按 3。不读 `scoring.md`。

## 返回

一次返回 JSON：`{prf_decision: {status, term, evidence, reason}}`。

`status` ∈ `none` / `pending` / `promoted` / `rejected` / `unevaluable`。`none` 时 `term` 空字符串、`evidence` 可省略。非 `none` 时 `term` 1–50 字，`reason` 1–500 字。`pending` / `promoted` 的 `evidence` 为 2–5 条 `{candidate_ref, source_field, quote}`。

## 支持词状态

- **活跃词**：可进主路径。
- **备用词**：救援时激活。
- **待试词**：只能进下一轮第二路，以 PRF 探针执行。
- **已拒绝** / **无法判定**：终态，终止使用；无法判定同时终止本次寻访。

## 先裁决已执行的待试词

已有 `prf_decision.status=pending` 且本轮第二路用了该 `term` 时，先按对账表改状态，再考虑是否抽新词。本轮没有在跑的待试词则跳过本段。

| 对账结果 | status |
| --- | --- |
| 第二路明确带来 ≥ 1 名新增可推荐，且没有明显噪音或方向漂移 | `promoted`（`term` / `evidence` 与上一轮 pending 相同） |
| 结果明确但未达上一行 | `rejected` |
| 证明未执行或未产生效果 | 保持 `pending` |
| 效果未知 | 保持 `pending`，`reason` 写明等待对账 |
| 已确认执行但详情全部失败或评分致命失败 | `unevaluable` |

## 再从简历抽新待试词

同时成立才抽：本轮已评分；当前没有待试词（含刚裁决后不再 pending 的）；没有致命错误或未对账；已完成轮数 < 3。否则不抽新词（保留上面的裁决；上面也没有则 `none`）。

种子：`labels` 里符合、总分 ≥ 75、必须满足 ≥ 70、风险不适用或 ≤ 45 的人，按总分取前 5；不足 2 人则 `none`。打开这些种子的详情，在至少 2 份工作或项目经历原文中逐字出现的技术、工具、框架、方法短语（如 "Flink CDC"），最多看 4 个，取第一个通过的，写成 `pending`。拒绝：已在需求关键词或已用词族中的；职责句、公司名、地点、学校、学历、薪资；只含标题的词、泛词；只出现在概括性总结里的词；在本轮不符合或总分 < 60 的人中出现比例 ≥ 0.4 的。`source_field` 只能是 `work_experience_summary` 或 `project_experience_summary`；`quote` 必须含该短语且逐字出自该字段。
