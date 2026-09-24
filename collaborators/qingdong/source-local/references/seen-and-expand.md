# 已看台账与轮内扩张

主 Agent 在步骤 10 读。台账回答「谁已经看过」，扩张回答「这一轮效果好时，再从同一批结果里多看谁」。两者都不改变轮次结构：每轮常规运行仍最多主路径 5 人、第二路 3 人。

## 已看台账

路径：`<TASK_WORK_DIR>/wts-local/seen.json`，只由 `ledger.py merge` 和 `adopt` 写入。检索子 Agent 每次运行前读它去重。

记进台账的是被**判过**的人：硬筛淘汰的、挑中评分的、读取失败的、判定为同一人另一份材料的。检索到但没挑中的可评者不进台账，留在 run 文件的 `remaining` 里，下一轮检索再遇到时照常可评。

- **失败可重看一次**：只失败过一次的人下一次运行可再选；第二次仍失败则跳过。
- **rejected 也算已看**：需求版本变化后不再重新硬筛，重评只针对评过分的人。
- **跨任务合并**：步骤 1 的 `adopt` 把上一次寻访的台账并入，这些人本次跳过，也不计入本次「看了几位」。
- **每次寻访结束**，台账路径由 settle 写进 `final-report-data.json` 的 `seen_ledger_path`，再照抄进 report.json。

## 轮内扩张

### 触发

第 1 轮在步骤 9 之后、第 2 轮起在步骤 8 之后，看最新回执的 `expansion_gate`：本次新评的人里可推荐占比 ≥ 50%，或新增强匹配 ≥ 2，且尚未成强池。为 true 即扩张，而不是进下一轮；为 false 照常走步骤 11。

每次扩张的回执再带一个 `expansion_gate`：仍为 true 且 `remaining` 里还有值得看的人，可以再扩一次；同一轮最多 3 次。扩张不计入轮次预算。

停止扩张的三种情况：扩张门不再成立；`remaining` 里没有值得挑的人；同一轮已扩 3 次。

### 挑人

从最新回执的 `remaining` 里挑（第一次扩张取本轮常规运行的回执，之后取上一次扩张的回执）。挑谁、挑几个由主 Agent 自己判断，依据只有每人一行的 `card` 和 `hard_filter`。三条建议，没有数量规定：

1. **不全看，挑认为比较可能的**。matched 和 unknown 之间不设先后，看 card 判断谁更像。
2. **按刚评完的人学**。本轮很匹配和值得推荐的人在 `scores.json` 的 `card` 上呈现什么共性（公司类型、职位写法、年限区间、技能词），优先挑符合这个共性的；和本轮低分候选人像的往后放。
3. **理由进决策记录**。每个被挑的 candidate_ref 一句依据（「同为大厂平台部门、职位写 Agent 平台」）；没被挑的不用写。

一次扩张最多 10 人，两路的人可以一起挑。每次扩张只派一个子 Agent，所以尽量一次挑够，少扩几次。

### 执行

写任务单 `briefs/iteration-N-expand-K.json`（K 从 1 递增）：

```json
{
  "mode": "expand",
  "iteration": 2,
  "expansion": 1,
  "run_file": "/ABSOLUTE/TASK_WORK_DIR/wts-local/runs/iteration-2-expand-1.json",
  "plan_file": "/ABSOLUTE/TASK_WORK_DIR/wts-local/search-plans/iteration-2.json",
  "requirements_file": "/ABSOLUTE/TASK_WORK_DIR/wts-local/requirements/v1.json",
  "seen_file": "/ABSOLUTE/TASK_WORK_DIR/wts-local/seen.json",
  "scores_file": "/ABSOLUTE/TASK_WORK_DIR/wts-local/scores.json",
  "source_run_file": "/ABSOLUTE/TASK_WORK_DIR/wts-local/runs/iteration-2.json",
  "picks": [{"candidate_ref": "local:/Users/x/简历/李四.pdf", "reason": "同为大厂平台部门"}],
  "prf": true,
  "prior_prf_decision": {"status": "pending", "term": "LangGraph", "evidence": [], "reason": ""},
  "completed_rounds": 1
}
```

`prior_prf_decision` 填上一轮定下的判定（与本轮常规运行的任务单相同），不填本轮已产生的判定。派发并 merge 后回到「触发」。扩张评出的人和常规轮的人一起进 Top 10 和目标公司池扩充。

### 播报

扩张前：「这轮找到的人质量不错，我再从这批结果里挑 N 位细看，期间不会有新消息。」扩张后并入步骤 8 的播报口径：这次又看了几人、新增几位值得推荐、几位很匹配。
