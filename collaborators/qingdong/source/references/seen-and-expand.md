# 已看台账与轮内扩张

步骤 1、9、10、11.5 读。台账回答"谁的详情已经打开过"，扩张回答"这一轮效果好时，再从同一页多看谁"。两者都不改变轮次结构：每轮仍最多主路径 5 份、第二路 3 份详情。

## 已看台账

路径：`<TASK_WORK_DIR>/wts/seen.json`。它是"已打开详情"的唯一事实来源；常规采集和扩张前，Agent 都对照它去重。

```json
{
  "merged_from": ["/ABSOLUTE/PREVIOUS_TASK_WORK_DIR/wts/seen.json"],
  "entries": [
    {
      "candidate_ref": "liepin:a1b2c3d4e5",
      "iteration": 1,
      "expansion": 0,
      "section": "details.primary",
      "result_ref": "result://TASK_ID/<sha256>",
      "detail_status": "matched",
      "opened_at": "2026-09-21T03:00:00Z"
    }
  ]
}
```

| 字段 | 内容 |
| --- | --- |
| `merged_from` | 从上一次寻访合并进来的台账路径；本次新建时为空数组 |
| `candidate_ref` | 与详情结果里的 `candidate_ref` 逐字一致 |
| `iteration` / `expansion` | 首次打开所在的轮次；常规轮 `expansion` 为 0，扩张为 K |
| `section` | `details.primary` / `details.secondary` / `details.expand` |
| `result_ref` | 打开它的那次运行的结果引用；评分条目的 `detail_ref` 直接用它 |
| `detail_status` | 详情硬筛状态 `matched` / `unknown` / `rejected`，采集失败写 `failed` |
| `opened_at` | 运行结果的 `finished_at` |

写入规则：

- **步骤 10 得到索引立刻追加**。索引每人一条，`detail_ref` 对应台账 `result_ref`，`detail_section` 对应 `section`，`finished_at` 对应 `opened_at`；轮次与扩张次数取本次执行值。失败者的 `detail_status` 为 failed。已在台账里的 candidate_ref 不重复追加，也不改写首次记录。
- **失败可重开一次**。只失败过一次的人下一轮可再选；第二次仍失败则跳过。
- **rejected 也算已看**。详情硬筛淘汰的人已经有详情，不需要再打开；需求版本变化后沿用原 `detail_ref` / `profile_path` 再派评分子 Agent 重评，不重新打开页面。
- **跨任务合并**。步骤 1 发现对话历史里有上一次寻访报告的 `seen_ledger_path` 时，把那份台账的 `entries` 全部并入本次，`merged_from` 记下来源。合并进来的人同样跳过。
- **每次寻访结束**，台账路径写进 `report.json` 的 `seen_ledger_path`（`references/final-report.md`）。

## 先挑人，再开详情

search 只读卡片，不开详情。Agent 用 browser_read_workflow_result 读完 `candidates.primary` 和存在的 `candidates.secondary`（有 next_offset 就继续），按 candidate_ref 对照台账去重，排除 rejected，两路间也去重；从剩余卡片挑选主路径最多 5 人、第二路最多 3 人。不要因为某人被跳过就新增台账记录。

把该次卡片结果的 result_ref 和两路名单写入 `iteration-N-collect.json`，格式见 `references/search-plan.md`，编译：

```
python "/ABSOLUTE/BUILTIN_SKILLS_DIR/wts/scripts/build_workflow.py" collect --task-id TASK_ID --iteration N --task-work-dir "/ABSOLUTE/TASK_WORK_DIR" --plan-file "/ABSOLUTE/TASK_WORK_DIR/wts/search-plans/iteration-N-collect.json"
```

再执行返回的 workflow_ref。collect 沿用原查询和筛选，重新定位列表，只打开名单内的人；列表变化后找不到的人不换人补位。无人可选的路径写 []，全部为空时也执行 collect，作为本轮完成记录。**补搜**发生在第一次采集之后、评分之前，见 SKILL.md 步骤 9；可采为 0 且将补搜时跳过第一次采集。扩张仍用评分后的 `labels`。采集完成后按 SKILL.md 步骤 10 运行 `score_inputs.py`，用它返回的索引追加台账，把 `profile_path` 交给评分子 Agent。搜索覆盖从 search 结果统计。

`coverage.skipped_seen` 由 Agent 统计本轮卡片中因台账被跳过的不同 candidate_ref 数。去重由 Agent 完成，Builder 不再生成排除谓词。

## 轮内扩张

### 触发

第 1 轮先完成 SKILL.md 步骤 11.3，用确认后的 `labels` 判断扩张门；第 2 轮起在步骤 11 评完新人后判断。**扩张门** = 本轮新人里可推荐占比 ≥ 50%，或本轮新增强匹配 ≥ 2，且尚未成强池（强池见 SKILL.md 步骤 14）。达到即扩张，而不是进下一轮；未达到照常走步骤 12。

扩张完成、评完扩张新人后再判断一次：仍达标且本页还有值得看的人，可以再扩一次；同一轮最多 3 次。扩张不计入轮次预算，也不改变"最大轮次 = min(轮次预算, 3)"。

停止扩张的三种情况：扩张门不再成立；本页没有值得挑的卡片了；当天累计打开的详情已达风控上限（默认 60，可由任务上下文覆盖）。第三种要播报原因。

### 挑人

挑谁、挑几个由 Agent 自己判断。依据是达标那条查询的 `candidates.<path>` 里规则初筛后的卡片信息：公司、职位、年限、城市、学历、技能摘要和卡片硬筛状态。只有三条建议，没有数量规定：

1. **不全开，挑认为比较可能的**。rejected 和台账里已有的一律不挑；matched 和 unknown 之间不设先后，看卡片内容判断谁更像。
2. **按刚评完的人学**。本轮强匹配和可推荐的人在卡片上呈现什么共性（公司类型、职位写法、年限区间、技能词），优先挑符合这个共性的卡片；和本轮低分候选人长得像的往后放。
3. **理由进决策记录**。每个被挑的 candidate_ref 一句依据（"同为大厂平台部门、职位写 Agent 平台"）；没被挑的不用写。

Builder 只设技术上限：一次扩张最多 30 人（首屏卡片数），同一轮最多 3 次扩张。

两路都达标时分别写两份扩张计划（K 递增），先扩主路径。

### 执行

按 `references/search-plan.md` 的扩张计划契约写 `iteration-N-expand-K.json`，编译：

```
python "/ABSOLUTE/BUILTIN_SKILLS_DIR/wts/scripts/build_workflow.py" expand --task-id TASK_ID --iteration N --expansion K --task-work-dir "/ABSOLUTE/TASK_WORK_DIR" --plan-file "/ABSOLUTE/TASK_WORK_DIR/wts/search-plans/iteration-N-expand-K.json"
```

调用一次 browser_run_workflow，按步骤 10 导出索引并追加台账，按步骤 11 只评新人（`detail_section` 写 `details.expand`，`scored_iteration` 写 N），再回到"触发"判断是否继续。扩张评出的人和常规轮的人一起进下一轮的 `decision_basis.candidate_scores`，也一起参与 Top 10 和目标公司池扩充。

### 播报

扩张前："这轮开出来的人质量不错，我再从这一页挑 N 位打开看看，预计 X 分钟，期间不会有新消息。"扩张后并入步骤 11 的播报口径：这次又看了几人、新增加几位值得推荐、几位很匹配。挑人依据留在决策记录里。
