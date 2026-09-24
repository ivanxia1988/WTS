# PRF（伪相关反馈）：先试后晋升

检索子 Agent 在任务单 `prf=true` 时读。PRF 是产生**待试词**的唯一来源；反思和救援只使用已有的词。待试词从高分简历的经历原文里抽。

## 本轮数据

- **本轮已评的人**：`scores_file` 当前需求版本里 `scored_iteration` 等于本轮 N 的人，加上这次运行刚评的人（重评时用重评后的分数）。总分按 `references/scoring.md` 的公式算。
- **本轮第二路**：`runs/iteration-N.json` 的 `paths.secondary`（这次就是常规轮时用你自己的检索结果）；其中 `path` 为 `secondary` 的已评者是第二路带来的人。
- 最大轮次按 3。

## 输出

run 文件的 `prf_decision`：`{status, term, evidence, reason}`。

`status` ∈ `none` / `pending` / `promoted` / `rejected` / `unevaluable`。`none` 时 `term` 为空字符串、`evidence` 可省略。非 `none` 时 `term` 1–50 字，`reason` 1–500 字。`pending` / `promoted` 的 `evidence` 为 2–5 条 `{candidate_ref, locator, quote}`。

同一轮里后一次运行的判定覆盖前一次，所以每次都按本轮全部数据重新判。

## 支持词状态

- **活跃词**：可进主路径。
- **备用词**：救援时激活。
- **待试词**：只能进下一轮第二路，以 PRF 探针执行。
- **已拒绝** / **无法判定**：终态，终止使用；无法判定同时终止本次寻访。

## 先裁决已执行的待试词

任务单 `prior_prf_decision.status=pending` 且本轮第二路的 `keywords` 含该 `term` 拆出的每个词时，先按对账表改状态，再考虑是否抽新词。本轮没有在跑的待试词则跳过本段，此时若 `prior_prf_decision` 是 pending，原样沿用。

| 对账结果 | status |
| --- | --- |
| 第二路明确带来 ≥ 1 名新增可推荐，且没有明显噪音或方向漂移 | `promoted`（`term` / `evidence` 与上一轮 pending 相同） |
| 结果明确但未达上一行（含 `NO_MATCHES`） | `rejected` |
| 第二路检索因限频或连接错误没有结果 | 保持 `pending`，`reason` 写明原因 |
| 第二路有结果，但挑中的人全部读取失败 | `unevaluable` |

## 再从简历抽新待试词

同时成立才抽：本轮已有评分；当前没有待试词（含刚裁决后不再 pending 的）；这次运行不是 `library_not_configured`；`completed_rounds` + 1 < 3。否则不抽新词（保留上面的裁决；上面也没有则 `none`）。

种子：本轮已评的人里符合、总分 ≥ 75、必须满足 ≥ 70、风险为 null 或 ≤ 45 的，按总分取前 5；不足 2 人则 `none`。在种子的工作经历或项目经历原文中，找至少在 2 份简历里逐字出现的技术、工具、框架、方法短语（如「Flink CDC」），最多看 4 个，取第一个通过的，写成 `pending`。

拒绝：已在需求关键词或已用词族中的；职责句、公司名、地点、学校、学历、薪资；只含标题的词、泛词；只出现在概括性总结或自我评价里的词；在本轮不符合或总分 < 60 的人中出现比例 ≥ 0.4 的。

`term` 照原文写法，可以含空格；主 Agent 写计划时按空格拆成几个词放进第二路，全部都要命中。

`quote` 必须含该短语，且逐字出自 `locator` 指向的工作或项目经历原文。
