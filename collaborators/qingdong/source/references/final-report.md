# 终态报告

步骤 15 读。先通过 Builder 的 `settle --iteration N` 读取最后已完成轮次和最终 decision_basis，生成 `<TASK_WORK_DIR>/wts/final-report-data.json`。市场观察使用市场求证子 Agent 的回传。N 是最后完成轮次，不创建额外搜索轮次。

## 内部记录

路径：`<TASK_WORK_DIR>/wts/report.json`。字段沿用报告原有的节名：

| 键 | 对应节 | 内容 |
| --- | --- | --- |
| `requirement_version` | — | 报告依据的需求版本 N |
| `results` | 【结果】 | Top 10 每人 `{candidate_ref, name, current_company, current_title, verdict: "符合" \| "不符合", total, must_have, nice_to_have, risk, basis, unknown_items: [], detail_url}` |
| `coverage` | 【搜索覆盖】 | `{rounds, queries: {primary, secondary}, seen, new, recommendable, strong, expansions: [{iteration, expansion, opened, recommendable, strong}], skipped_seen, company_words: [{word, new_candidates}], refills: [{company, eligible, refilled}], pool_size: {initial, from_candidates}, prf: {promoted: [], rejected: []}, degraded_filters: []}`；`seen` 含扩张打开的人，`skipped_seen` 是因已看台账被跳过的卡片数 |
| `seen_ledger_path` | — | 本次已看台账 `<TASK_WORK_DIR>/wts/seen.json` 的绝对路径，供下一次寻访（步骤 16 选了备选方向后）合并 |
| `not_recommended` | 【未推荐摘要】 | `{count, reasons: [{reason, count}]}`，看过但没进推荐名单的人按主要原因聚合，不列个人 |
| `verify_in_interview` | 【面试核实项】 | 照录需求版本的 `verify_in_interview`，提醒用户这些条件没有参与筛选 |
| `stop_reason` | 【停止原因】 | 强匹配足够 / 新增候选不足 / 多轮无进展 / 达到最大轮次 / 词族耗尽 / 预算，取一 |
| `unmet` | 【未满足原因】 | `{gap_to_target, exhausted_families: [], unverifiable_hard_filters: []}` |
| `failures` | 【失败项】 | `{candidate_ref, reason}`，含详情采集失败和没有 detail_url 的 |
| `market_insights` | 【市场洞察】 | `{skills, profile, company_sources}` 三小节全文，见下 |

两条硬规则：`detail_url` 来自运行结果，没有的进 `failures`；猎聘上的人数和分数来自运行结果和评分记录。公开资料的判断来自市场求证回传，不拿来改这些数字。

## 用户视图模板

```text
# 寻访报告

找了 <rounds> 轮，看了 <seen> 位候选人，其中 <recommendable> 位值得推荐、<strong> 位很匹配。

推荐名单（按总分降序）：

| 序号 | 候选人概况 | 推荐程度 | 评分 | 推荐依据 | 待核实项 | 详情 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | <name> · <公司／职位／学历／年限> | <很匹配／值得推荐> | <total>（<must_have>／<nice_to_have>／<risk>） | <basis 一句白话> | <unknown_items；无则写“无”> | [查看猎聘详情](detail_url) |

评分括号内依次为必须满足、加分项、风险；不适用写“不适用”。

看过但没推荐的：<not_recommended.count> 位，主要是<reasons 前两三项的白话，如"缺 Agent 落地经历（4 位）、城市不符（2 位）">；为 0 则省去本节

为什么停下：<stop_reason 的白话，如"能想到的搜法都试过了" / "匹配的人已经够了" / "连续两轮没有新人">

还差什么：<gap_to_target 为 0 时省去本节；否则一句话说差几位、哪些条件在市场上很难同时满足>

没看到简历的：<failures 数量> 位，<原因白话>；为空则省去本节

面试时请核实：<verify_in_interview 一行列举，这些条件简历看不出来，没参与筛选>；为空则省去本节

市场观察：
- 技能：<skills 小节的结论，两三句>
- 这类人的特征：<profile 小节的结论，两三句>
- 公司来源：<company_sources 小节的结论，两三句>
```

渲染规则：推荐名单使用 Markdown 表格，不放在代码块中；只列符合且总分 ≥60 的人，每人一行，没有则写“本次暂无可推荐人选”。公司、职位、学历和年限只用结果中已有信息，缺失写“未提供”；单元格中的竖线转义，换行合为空格。`failures` 每人计入数量；`not_recommended` 只出数量和原因，不出现任何个人；"找了 N 轮"里的轮数不含扩张和补搜，"看了 N 位"里的人数含扩张和补搜。候选人的 candidate_ref、PRF 词、补搜记录、站内筛选降级项、扩张次数都留在文件里，用户视图不出现。报告输出后直接进入步骤 16 的方向选择。

## 市场洞察

给猎头的知识沉淀，回答"这个岗位的市场长什么样"。猎聘上的人数、分数、命中公司用本次结果。公开资料用市场求证子 Agent 的回传，每条判断带来源。两边分开写，例如"这次看的人里 4 位有 RAG；公开 JD 里这是常见要求（来源）"。

1. **核心技能**（`skills`）：JD 的必须满足 vs 这次可推荐候选人的高频技能，再对照公开资料。标出两类差异：JD 要求但这次的人普遍没有的，这次的人普遍有但 JD 没提的。
2. **高分候选人特征**（`profile`）：这次样本的 title、工作年限、技能组合、项目类型、公司类型、当前城市。可推荐不足 3 人时，这次样本写"样本不足，不做归纳"，公开资料仍可写。性别、学校名称、民族、婚育不写入。
3. **公司来源**（`company_sources`）：这次高分候选人来自哪些公司，对照步骤 3.5 的目标公司和公开资料里常见的雇佣方。写清调研时认为该去哪、猎聘上实际有多少人、最后从哪找到。
