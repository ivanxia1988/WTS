# 终态报告

主 Agent 在步骤 13 读。人数、分数、Top 10 只取 `ledger.py settle` 写出的 `<TASK_WORK_DIR>/wts-local/final-report-data.json`；市场观察的公开资料取步骤 13 自己做的市场求证。不重新检索、不重新评分。

## 内部记录

路径：`<TASK_WORK_DIR>/wts-local/report.json`。字段沿用报告原有的节名：

| 键 | 对应节 | 内容 |
| --- | --- | --- |
| `requirement_version` | — | 照抄 settle 结果 |
| `results` | 【结果】 | settle 的 `top10` 每人 `{candidate_ref, name, current_company, current_title, verdict: "符合" \| "不符合", total, must_have, nice_to_have, risk, basis, unknown_items: [], file_path, locator}`；`name` 等取自 `card`，`basis` 由 `evidence_summary` 改写成一句白话 |
| `coverage` | 【搜索覆盖】 | `{rounds, queries: {primary, secondary}, seen, recommendable, strong, expansions: [{iteration, expansion, picked, recommendable, strong}], skipped_seen, company_words: [{word, new_candidates}], refills: [{company, eligible, refilled}], pool_size: {initial, from_candidates}, prf: {promoted: [], rejected: []}, coverage_warnings: []}`；`rounds`、`seen`、`recommendable`、`strong`、`coverage_warnings` 照抄 settle，其余取自各次回执 |
| `seen_ledger_path` | — | 照抄 settle 结果，供下一次寻访（步骤 14 选了备选方向后）合并 |
| `not_recommended` | 【未推荐摘要】 | `{count, reasons: [{reason, count}]}`：settle 的 `not_recommended` 按 `short_reason` 归并，加上 `hard_filter_rejected` 按 `reason` 归并；不列个人 |
| `verify_in_interview` | 【面试核实项】 | 照录需求版本的 `verify_in_interview`，提醒用户这些条件没有参与筛选 |
| `stop_reason` | 【停止原因】 | 强匹配足够 / 新增候选不足 / 多轮无进展 / 达到最大轮次 / 词族耗尽 / 预算，取一 |
| `unmet` | 【未满足原因】 | `{gap_to_target, exhausted_families: [], unverifiable_hard_filters: []}` |
| `failures` | 【失败项】 | 照抄 settle 的 `failures` |
| `market_insights` | 【市场洞察】 | `{skills, profile, company_sources}` 三小节全文，见下 |

## 用户视图模板

```text
# 寻访报告

在本地简历库找了 <rounds> 轮，看了 <seen> 位候选人，其中 <recommendable> 位值得推荐、<strong> 位很匹配。

推荐名单（按总分降序）：

| 序号 | 候选人概况 | 推荐程度 | 评分 | 推荐依据 | 待核实项 | 简历位置 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | <name> · <公司／职位／学历／年限> | <很匹配／值得推荐> | <total>（<must_have>／<nice_to_have>／<risk>） | <basis 一句白话> | <unknown_items；无则写“无”> | <简历位置> |

评分括号内依次为必须满足、加分项、风险；不适用写“不适用”。

检索覆盖不完整：<coverage_warnings 的白话>；为空则省去本节

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

**简历位置**：PDF / Word 写成 `[<文件名>](file://<file_path>)`；Excel 写成 `[<文件名>](file://<file_path>) 的「<sheet 名>」第 <行号> 行`。路径里的空格按 URL 编码写成 `%20`。

渲染规则：推荐名单使用 Markdown 表格，不放在代码块中；只列符合且总分 ≥ 60 的人，每人一行，没有则写“本次暂无可推荐人选”。公司、职位、学历和年限只用 `card` 里已有信息，缺失写“未提供”；单元格中的竖线转义，换行合为空格。`failures` 每人计入数量；`not_recommended` 只出数量和原因，不出现任何个人；"找了 N 轮"里的轮数不含扩张和补搜，"看了 N 位"里的人数含扩张和补搜、不含上一次寻访合并来的人。candidate_ref、PRF 词、补搜记录、扩张次数都留在文件里，用户视图不出现。报告输出后直接进入步骤 14 的方向选择。

## 市场洞察

给猎头的知识沉淀，回答"这个岗位的市场长什么样"。本地库里的人数、分数、命中公司用本次结果。公开资料用市场求证的结论，每条判断带来源。两边分开写，例如"这次看的人里 4 位有 RAG；公开 JD 里这是常见要求（来源）"。本地库只是用户自己整理过的简历，归纳时说「这批简历里」，不说「市场上」。

1. **核心技能**（`skills`）：JD 的必须满足 vs 这次可推荐候选人的高频技能，再对照公开资料。标出两类差异：JD 要求但这次的人普遍没有的，这次的人普遍有但 JD 没提的。
2. **高分候选人特征**（`profile`）：这次样本的 title、工作年限、技能组合、项目类型、公司类型、当前城市。可推荐不足 3 人时，这次样本写"样本不足，不做归纳"，公开资料仍可写。性别、学校名称、民族、婚育不写入。
3. **公司来源**（`company_sources`）：这次高分候选人来自哪些公司，对照步骤 4 的目标公司和公开资料里常见的雇佣方。写清调研时认为该去哪、本地库里实际有多少人、最后从哪找到。
