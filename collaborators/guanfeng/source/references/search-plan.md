# 搜索计划契约

仅在生成或调整猎聘搜索计划时读取本文件。计划文件是 Agent 与 Skill Builder 之间的领域输入，不是浏览器命令。Builder 会拒绝未知字段，并把计划与 Skill 内的渠道资产编译为 `browser.workflow.v1`。

搜索计划轮次允许 1-5。第一轮必须直接创建 `iteration-1.json`，后续轮次依次使用 `iteration-2.json`……`iteration-5.json`。第 N 轮计划的唯一合法路径是：

```text
<TASK_WORK_DIR>/wts/search-plans/iteration-N.json
```

`iteration-0` 只用于 preflight，不存在 `iteration-0.json` 搜索计划。首次创建用 write_file，同轮修正用 edit_file；write_file 不覆盖现有文件。不要创建 `v2`、`v3`、`draft` 或临时副本，也不要回改已执行的历史计划。Builder 会同时校验任务工作目录、1-5 轮次和文件名，不符合即拒绝编译。

第 1 轮只能有主路径。第 2 轮起可以增加第二路；两路查询不能相同。一次编译会把本轮两路连续写进同一份工作流。

## 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `requirement_version` | string | 从第 1 轮起填写已确认版本（如 v1），与 decision_basis 一致；旧计划省略时沿用 basis 版本或 v1 |
| `primary_query` | string | 必填，1-50 字符；主路径自然语言查询，不使用 `OR`、`AND`、`NOT` |
| `secondary_query` | string | 可选；第二路自然语言查询。第 1 轮禁止出现 |
| `site_filters` | object | 猎聘页面可直接设置的筛选条件 |
| `hard_filters` | object | Builder 将其编译为通用 `data.filter` 谓词；先做卡片预筛，再做详情终筛 |
| `semantic_criteria` | object | 给逐候选语义评分用，不编译进页面动作 |
| `limits.max_cards_per_path` | integer | 1-30，默认 30；每路首屏最多抽取的卡片数 |
| `limits.primary_max_details` | integer | 0-3，默认 3 |
| `limits.secondary_max_details` | integer | 0-2，默认 2；没有第二路时视为 0 |
| `action_delay_ms` | integer | 800-5000，默认 1200；注入页面操作程序，不由 Agent 逐步等待 |
| `decision_basis` | object | 当前需求版本下已完成的评分与本轮既定方向；从第 2 轮起必须填写 |

兼容：若没有 `primary_query`，可以把旧字段 `keyword_text` 当作主路径查询。不要同时写两个且内容不一致。每路固定只采首屏，`limits.max_pages` 会被忽略并固定为 1。

`semantic_criteria` 只接受：

- `must_have`：必须满足，最多 20 条
- `nice_to_have`：加分项，最多 20 条
- `exclude_signals`：排除信号，最多 20 条

## 评分与决策复用

`decision_basis` 与搜索计划同一次写入，不另开模型调用来“复核上一轮”。评分的语义判断仍由 Root 完成；Builder 按原公式计算总分、推荐/强匹配人数和 Top 10，核验原始详情引用及 PRF 引文。计划快照保存在不可变工作流的元数据中，不作为浏览器动作执行。后续轮次和结算以实际执行完成的快照为校验依据；旧工作流无快照时兼容读取历史计划。

输入使用 `site_filters` 和 `decision_basis.candidate_scores`。`site_filter_fields`、`decision_receipt.scores/counts/top10/prf` 是输出字段，不能复制回 SearchPlan 或 decision_basis。Builder 仅有 preflight/search/settle，没有 reflect 子命令。

```json
{
  "requirement_version": "v1",
  "completed_iteration": 1,
  "candidate_scores": [
    {
      "candidate_ref": "liepin:实际候选人ID",
      "detail_ref": "result://实际任务ID/实际64位结果摘要",
      "detail_section": "details.primary",
      "scored_iteration": 1,
      "matches": true,
      "must_score": 80,
      "nice_score": 70,
      "risk_score": 10,
      "unknown": ["缺少明确证据的硬条件"],
      "evidence_summary": "按必须满足、加分和风险分别记录简短证据依据，不贴整份简历"
    }
  ],
  "prf_decision": {"status": "none", "reason": "没有满足经历证据条件的新短语"},
  "next_action": {
    "iteration": 2,
    "primary_query": "与计划 primary_query 完全一致",
    "secondary_query": "与计划 secondary_query 完全一致，无第二路则省略",
    "reason": "根据已完成结果选定这一方向的原因"
  }
}
```

填写约定：

- `requirement_version` 是已确认需求版本的非空字符串；同版本的 `semantic_criteria` 和 `hard_filters` 从第 1 轮起保持一致，站内筛选可合理调整。换搜索词只改查询字段，不能随之替换或删除 required_keyword_groups。版本变化时逐人按新版本重评并写 `correction_reason`，不能为了通过校验只换版本号或回改上一轮计划。
- 下一轮搜索计划的 `completed_iteration` 必须是 `iteration - 1`。`candidate_scores` 保存截至该轮全部已评候选人，含低分、不符合和退出 Top 10 的人；同版本按 `candidate_ref` 唯一，不追加重复记录。
- `scored_iteration` 是候选人**首次评分轮次**，纠错或版本重评不修改；`matches=true` 表示符合、没有明确硬冲突，`false` 表示存在明确硬冲突；不能用低分或 unknown 代替不符合。
- 三维分数只接受 0–100 的整数，不接受布尔值、字符串或小数。必须满足分必填；有加分项/排除信号时对应分数必填，没有时填 `null`，按原规则剔除该维度权重，不能用 0 替代“不适用”。不要传 `total`、排名或人数让 Builder 照抄。
- `detail_ref`、`detail_section`、`candidate_ref` 必须指向当前任务真实保存的唯一详情。Builder 核对 Result Store 摘要与详情硬筛状态；`evidence_summary` 简述三维依据，`unknown` 是文本数组，没有则 `[]`。
- 沿用最近计划的已完成条目，只补新候选人。需求变更、新详情、具体事实或计算错误可以修正已有条目；同版本修正必须填写 `correction_reason`，不能为了维持播报数字改分。连续工具之间从现有上下文或计划复用，不要求每步再读取计划。

`prf_decision.status` 接受 `none`、`pending`、`promoted`、`rejected`、`unevaluable`。`reason` 必填；除 `none` 外必须填写 `term`。`none` 和 `rejected` 是正常决策，不能因为没有新词而重新搜索或重评。

`pending` 必须带 `evidence` 数组，每项为 `{"candidate_ref":"...","source_field":"project_experience_summary","quote":"包含该短语的原文短引文"}`。证据须来自当前排名前 5 位有效种子中的至少 2 位不同候选人，只接受 `work_experience_summary` / `project_experience_summary`；Builder 核对种子门槛、来源字段及逐字引文。自评、技能、标题不能替代经历证据。

负样本按本轮实际评分的不符合或总分低于 60 的候选人计数，匹配范围固定为详情中提取的工作/项目经历、自评、技能、卡片摘要、职位标题、求职意向及教育/语言/基础资料等文本，包含 `self_summary`；大小写不敏感，同一人只计一次。没有负样本时不触发比例门槛；出现比例达到 0.4 的词应记 `rejected`。不要将宣称 `pending` 却不满足证据条件的错误理解成“可以略过规则”。已使用词族、泛词和语义漂移的排除仍由 Agent 判断并记录。

`promoted` 必须承接上一计划同版本的待试词及原始证据，并有第二路新增可推荐候选人；晋升后保留原证据。Builder 不替代对噪音或方向漂移的语义判断。

写入成功 → 编译 → 消费 `decision_receipt` → 执行返回的 `next_action.workflow_ref`。只有新事实、用户更改或具体错误才回头修改决策；写文件和编译成功本身不提供新的业务证据。

### 最后一轮结算

停止时将最新完整 `decision_basis` 保存为 `<TASK_WORK_DIR>/wts/final-decision.json`，保留当前搜索计划，不能覆盖它来丢掉上一轮的评分依据。快照中 `completed_iteration` 为刚完成的轮次，`next_action` 仅为 `{"action":"report","reason":"确定性停止原因"}`。运行：

```text
python "<BUILTIN_SKILLS_DIR>/wts/scripts/build_workflow.py" settle --task-id TASK_ID --iteration N --task-work-dir "<TASK_WORK_DIR>"
```

N 是最后完成的轮次（1–5），不是下一轮；第 5 轮后仍填 5，不创建 iteration-6.json。省略 --plan-file/--decision-file 时自动取上述约定路径；显式传入错误路径仍会拒绝。

该模式读取本地计划和结果、校验评分并返回相同 `decision_receipt`，不编译或执行新的浏览器工作流，同时生成 `report_data_file`（`<TASK_WORK_DIR>/wts/final-report-data.json`）。其中 candidates 是 Top 10，包含真实姓名、detail_url、三维分数/总分、证据摘要及 unknown，均来自已校验的评分和详情引用；null 保持缺失，不编造链接。读取该文件即可编写报告，无需临时脚本扫描 Result Store 或重评。

## 站内筛选字段

`site_filters` 支持：

- `current_cities`、`expected_cities`: 最多 9 个城市名称或标准编码。
- `experience_years`: 仅支持 `{min:0,max:0}`、`{min:1,max:3}`、`{min:3,max:5}`、`{min:5,max:10}`、`{min:10,max:null}`。
- `education`: 最多一个值，支持本科、硕士、博士/博士后、大专、中专/中技、高中及以下。
- `school_requirements`: 最多一个值，支持 `211`、`985`、`double_first_class`、`overseas`。
- `company`: 最多一个公司名称关键词的字符串数组，例如 `["字节"]`。仅使用用户已确认的名称；公司为硬条件时，同时写入 `hard_filters.company`。
- `activity_recency`、`job_hop_frequency`: 单个预设字符串，见下方映射；未指定或不限时省略。只用于站内筛选，不支持放入 `hard_filters`。

策略允许写入但页面没有控件的字段：

- `work_content`: 写入 `site_filters` 时 Builder 会记 `SITE_FILTER_UNSUPPORTED` 并跳过页面筛选；请同时写入 `hard_filters` 做文本硬筛。

- `age_range`：`{min,max}` 整数对象，边界取 16-60，至少给一个边界（如 `{min:25,max:35}`、`{min:28,max:null}`）。仅用于站内筛选，不得写入 `hard_filters`。
- `gender`：单个值，支持 `male`、`female` 或中文 `男`、`女`；不限时省略字段。仅用于站内筛选，不得写入 `hard_filters`。

年龄、性别只能作为站内筛选缩小召回范围，不参与硬筛、评分或排序；这两个条件没有本地硬筛回退，页面操作失败时按 `unsupported_filters` 报告未验证，不得当作已满足。

除公司联想输入外，站内筛选使用猎聘支持的离散预设。Selector、控件定位、弹窗交互和取值标签由 Skill 渠道资产维护，计划中不得出现 Selector 或点击步骤。不要为了表达 `0-3 年` 等精确范围而选近似预设；把精确条件保留在 `hard_filters`。若站内工作年限不是受支持的预设，Builder 只会在 `hard_filters` 存在完全相同范围时移除该站内条件并返回 warning，否则拒绝计划。

所有站内筛选都采用“失败后继续并上报”：某个字段的页面操作失败时跳过该字段、继续后续搜索，并把字段、请求值和错误原因写入对应路径的 `search.<path>.unsupported_filters`。站内筛选只是缩小召回范围；同字段若有受支持的硬条件，仍由后续卡片和详情 `data.filter` 执行。活跃度、跳槽频率没有自动硬筛回退，失败记录的 `context.hard_filter_fallback` 为 false，必须说明条件未验证，不能把结果当作已满足该条件。计划不再需要 `allow_partial_filters`。

### 活跃度与跳槽频率

仅在用户明确指定时填写，不根据岗位名称、默认排除信号或模型偏好自行添加。“近 1 年内多次跳槽”与下面的站点预设含义不同，不能自动替换。

| 字段 | 计划值 | 页面选项 |
| --- | --- | --- |
| `activity_recency` | `today` | 今天活跃 |
| `activity_recency` | `within_3_days` | 3天内活跃 |
| `activity_recency` | `within_7_days` | 7天内活跃 |
| `activity_recency` | `within_30_days` | 30天内活跃 |
| `activity_recency` | `within_3_months` | 最近三个月活跃 |
| `activity_recency` | `within_6_months` | 最近半年活跃 |
| `activity_recency` | `within_1_year` | 最近一年活跃 |
| `job_hop_frequency` | `last_5_years_max_3` | 近5年不超过3段 |
| `job_hop_frequency` | `last_3_years_max_2` | 近3年不超过2段 |
| `job_hop_frequency` | `recent_2_jobs_min_2_years_each` | 近2段均不低于2年 |

例如用户明确要求“3 天内活跃、近 3 年不超过 2 段”时，合并进当前计划的筛选部分：

```json
{
  "site_filters": {
    "activity_recency": "within_3_days",
    "job_hop_frequency": "last_3_years_max_2"
  }
}
```

两项都是自定义下拉：先按“活跃度”或“跳槽频率”所在筛选行定位唯一触发器，再展开、等待可见 portal 浮层，只在唯一浮层内点击文本完全相同的唯一选项。点选即提交，不增加“确定”步骤。点击后同时检查下拉收起、框内显示所选值、底部筛选标签出现、结果加载结束，再等待列表稳定；人数可以不变，零结果也有效。

`locator: null` 只表示快照没有给出推荐定位，不等于 DOM 无法通过 CSS 查询；portal 也不必然意味着不在可访问性树中。Builder 复用渠道资产中的 DOM 选择器，不依赖快照是否列出了菜单项。每步重新解析定位；不保存本轮 ref、`rc_select_x` 序号或截图坐标。定位缺失、歧义或验证超时时报告筛选降级，不用历史坐标重试。

### 公司名称筛选

公司名称是 Ant Design combobox，视觉上的“搜索公司”不是可靠的 input placeholder，不能用 textbox 或该 placeholder 定位。实测的 `#rc_select_4` 仅对当时页面有效；运行时编号会漂移，也不代表视觉顺序，不得固化编号或按第几个 combobox 猜测公司框。

Builder 在带“公司名称”文案的筛选行内定位唯一的 `input[role='combobox']`，输入后读取当前控件的 `aria-controls`（兼容 `aria-owns`），仅在关联的 portal 下拉框内选择文本完全相同的唯一候选。不会全页点击同名文本、复用旧 ref/坐标或盲选第一个公司；没有精确候选或定位有歧义时记录筛选降级。

固定流程：聚焦并输入 → 等待联想 → 点击同名候选 → 确认框内已选公司 → 再激活公司框 → 点击该行的“确 定” → 检查框内公司、底部已提交筛选标签、URL 包含 `#session`，并等待结果加载结束及列表稳定。仅填入文本不算生效。`#session` 可能在前面的关键词搜索后就已存在，结果人数也可能不变，不能把这两项单独当成公司筛选成功的依据；零结果是有效结果，不要求“3000+”。

现有实测只覆盖单公司，尚未确认页面的多公司 OR 行为，因此 `site_filters.company` 最多一个值。用户要求多公司任一背景时，完整名单写入 `hard_filters.company`，省略站内公司条件；只有用户明确要求限定单一公司时才缩窄页面范围。公司类型或偏好不转换成未确认的公司名。

## 硬性过滤字段

`hard_filters` 支持：

- `current_cities`、`expected_cities`、`education`: 字符串数组。
- `experience_years`: `{min,max}`。
- `school_requirements`: 字符串数组，支持 `211`、`985`、`double_first_class`、`overseas`；数组内按“满足任一项”判断。
- `company`、`work_content`: 字符串数组；卡片阶段缺失或未命中记 unknown，详情阶段未命中记不符合。
- `required_keywords.all`: 必须全部命中的关键词数组。
- `required_keywords.any`: 至少命中一个的关键词数组。
- `required_keyword_groups`: 二维字符串数组。组与组之间是 AND，每组内部是 OR。

编译后的顺序固定为：对每一路执行关键词搜索并应用站内筛选，抽取该路首屏最多 30 张卡片，使用卡片已知字段做硬性预筛，只为 `matched` 和 `unknown` 候选人按该路详情预算采集详情，再使用详情字段做硬性终筛。第 2 轮起若有第二路，同一份工作流会接着跑完第二路。所有步骤由一次 `browser_run_workflow` 在模型外连续执行。

卡片上能够明确读到的城市、学历、工作年限等字段可以直接淘汰不符合者。列表摘要没有出现关键词、院校标签或其他可能被页面折叠的信息时只记为 `unknown`，不得提前淘汰。Builder 为卡片和详情分别生成声明式谓词；通用浏览器不理解招聘字段。

用户或 JD 明确声明为硬性、且属于上述支持字段的站内条件必须同步写入 `hard_filters`。活跃度、跳槽频率当前只有站内预设，不能写入未知硬筛字段或把页面失败包装为硬筛通过。不要假设站内筛选等同于最终硬筛。

## 结果分区

工作流按路径落盘，不要把两路结果混成一个无标记列表：

- `summary.paths.primary` / `summary.paths.secondary`
- `search.primary` / `search.secondary`
- `candidates.primary` / `candidates.secondary`
- `details.primary` / `details.secondary`
- `failures.primary` / `failures.secondary`

卡片和详情会带 `search_path=primary|secondary`。没有第二路时，不要读 `secondary` 分区。

使用 browser_read_workflow_result 读取详情，建议 limit=3（工具会自动缩小过长页面）。返回条数可能小于 limit，has_more=true 时按 next_offset 续读；字段为 null 表示缺失，不是工具失败。

## 示例

第 1 轮只有主路径：

```json
{
  "requirement_version": "v1",
  "primary_query": "AI Agent LangGraph",
  "site_filters": {
    "expected_cities": ["上海"],
    "education": ["本科"]
  },
  "hard_filters": {
    "expected_cities": ["上海"],
    "education": ["本科"],
    "required_keyword_groups": [["AI Agent"], ["LangGraph", "LangChain"]]
  },
  "semantic_criteria": {
    "must_have": ["有大模型应用或 Agent 落地经历"],
    "nice_to_have": ["熟悉 RAG"],
    "exclude_signals": ["纯销售岗"]
  }
}
```

第 2 轮主路径 + 第二路（这里只展示搜索字段；新任务还需填写上面的 `decision_basis`）：

```json
{
  "requirement_version": "v1",
  "primary_query": "AI Agent LangGraph RAG",
  "secondary_query": "AI Agent 向量检索",
  "site_filters": {
    "expected_cities": ["上海"]
  },
  "hard_filters": {
    "expected_cities": ["上海"],
    "education": ["本科"],
    "required_keyword_groups": [["AI Agent"], ["LangGraph", "LangChain"]]
  },
  "semantic_criteria": {
    "must_have": ["有大模型应用或 Agent 落地经历"],
    "nice_to_have": ["熟悉 RAG"],
    "exclude_signals": ["纯销售岗"]
  }
}
```
