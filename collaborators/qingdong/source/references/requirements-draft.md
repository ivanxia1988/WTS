# 需求确认稿与候选人画像

步骤 4 读。确认稿是给 Agent 的规格，写成 JSON 文件；画像是确认稿的白话投影，展示给用户。Agent 只编辑确认稿，画像每次都从确认稿重新渲染。

## 确认稿文件

路径：`<TASK_WORK_DIR>/wts/requirements/vN.json`，N 从 1 起，每次修改写新的 N，旧版本保留。**当前需求版本**就是 N 最大的那份。

字段沿用确认稿原有的节名：

| 键 | 对应节 | 内容 |
| --- | --- | --- |
| `version` | — | 整数 N |
| `key_judgments` | 【关键判断】 | 3–6 条 `{kind, judgment, basis}`，kind ∈ `anchor` / `must_have` / `conflict` / `assumption`；剩余 [假设] 全部以 `assumption` 列出 |
| `position` | 【岗位】 | `{title, primary_anchor, secondary_anchor, anchor_source: "title" \| "jd_summary", level_years}` |
| `mission` | 【岗位使命】 | 一句话 |
| `must_have` | 【必须满足】 | ≤8 条 `{text, source, evidence_section}`，source 如 "JD 第 n 条" / "用户确认"；evidence_section 是优先取证区块，取 工作经历 / 项目经历 / 技能 / 教育经历 / 自我评价 之一 |
| `nice_to_have` | 【加分项】 | `{text, evidence_section}` 数组，按重要性排序 |
| `verify_in_interview` | 【面试核实项】 | `{text, source}` 数组；简历通常看不出来的要求（顶会论文、绩效、口碑、抗压等），不评分、不筛选 |
| `exclude_signals` | 【排除信号】 | `{text, default: bool}` |
| `hard_filters` | 【硬性筛选条件】 | `{location, education, experience_years, company, school_requirements, work_content}`，未指定写 `"不限"` |
| `keywords` | 【检索关键词】 | `{active: [{word, family}], reserve: [{word, family}]}`，active ≤6、reserve ≤2 |
| `non_search_terms` | 【不做搜索词】 | `{text, destination: "评分" \| "筛选" \| "不用"}` |
| `cities` | 【城市】 | `{A: [], B: [], C: []}` |
| `target_companies` | 【目标公司】 | `{source: "JD" \| "research" \| "unlimited", companies: [{name, category, confidence, source}], categories: [string]}`，companies 顺序即目标公司池初始清单：用户自定义的在前，勾选的调研公司按推荐顺序在后 |
| `main_pool` | 【主池】 | `{name, title_scope, company_tier, city_tier, extra}` |
| `notes` | 【备注】 | `{boilerplate: [], unblocking_unspecified: []}` |

备选方向照旧只在决策记录里，文件中没有。

## 画像模板

以普通文本输出，版本号只在文件里；修改后重新呈现时开头加一句"已按您的意见改好，请再看一眼："。

```text
# 候选人画像

一句话：<城市 A> 的 <title>，<年限>，<有目标公司时："最好来自 X、Y 这类" + 类别>。

这个人要有：
- <每条 must_have 一行白话；hard_filters 里非"不限"的项也各一行>

有这些更好：<nice_to_have 一行列举；为空则省去本行>

这些人不要：<每条 exclude_signals 一行列举>

这些简历看不出来，我不拿它们打分，留给面试核实：<verify_in_interview 一行列举；为空则省去本行>

我做了几个判断，请确认：
- <每条 key_judgments 一行："判断 + 依据"，assumption 用"我按……理解"句式>
- <notes.boilerplate 非空时加一行："X、Y 这类要求我没当硬条件，需要的话告诉我">

搜索时我会用这些词：<keywords.active 的 word，加目标公司池排第一的公司名>
```

## 渲染规则

- **决策无损**：`must_have`、非"不限"的 `hard_filters`、`exclude_signals`、`verify_in_interview` 每条都在画像里有一行；`key_judgments` 每条都在"我做了几个判断"里有一行。渲染完逐条核对，缺一条就补一行再呈现。JD 里的要求只能落在这几个桶之一，不能因为简历上看不出来就悄悄删掉。
- **只出白话**：来源标注、词族、活跃/备用、置信度数字、城市 A/B/C 字母、[CONFLICT] / [过载] / [套话] / [假设] 标记、title 范围｜公司层｜城市层字段名，都留在文件里。公司类别只作"这类"的修饰，不单列。学历下限写成「本科及以上」这种说法；用户写明只要某一档时，写成「只要本科」。
- **改稿再渲染**：用户要改某处时，改 JSON、`version` +1、写新文件，然后重新渲染完整画像再次请求确认。
