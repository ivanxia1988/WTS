# 搜索计划契约

按当前步骤读对应的节：

- 写 `iteration-N.json`（步骤 7）：字段、站内筛选、硬性过滤，对照文末示例。
- 步骤 9 补搜：补搜计划。
- collect（步骤 9）：常规详情名单。
- 步骤 11.5：扩张计划。步骤 10：结果分区。

计划文件是 Agent 与 Skill Builder 之间的领域输入，不是浏览器命令。Builder 会拒绝未知字段，并把计划与 Skill 内的渠道资产编译为 `browser.workflow.v1`。

搜索计划轮次允许 1-3。第一轮必须直接创建 `iteration-1.json`，后续轮次依次使用 `iteration-2.json`、`iteration-3.json`。第 N 轮计划的唯一合法路径是：

```text
<TASK_WORK_DIR>/wts/search-plans/iteration-N.json
```

`iteration-0` 只用于 preflight。同一轮修正时原地覆盖同一个 `iteration-N.json`。Builder 会同时校验任务工作目录、1-3 轮次和文件名，不符合即拒绝编译。

第 1 轮只能有主路径。第 2 轮起可以增加第二路；两路查询不能相同。一次编译会把本轮两路连续写进同一份工作流。

## 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `requirement_version` | string | 从第 1 轮起填写已确认需求版本；同版本条件保持一致 |
| `primary_query` | string | 必填，1-50 字符；主路径自然语言查询，不使用 `OR`、`AND`、`NOT`。可含 1 个公司词（SKILL.md 步骤 3.5） |
| `secondary_query` | string | 可选；第二路自然语言查询，只含锚点和支持词。第 1 轮禁止出现 |
| `site_filters` | object | 猎聘页面可直接设置的筛选条件 |
| `hard_filters` | object | Builder 将其编译为通用 `data.filter` 谓词；先做卡片预筛，再做详情终筛 |
| `semantic_criteria` | object | 给隔离评分用，不编译进页面动作 |
| `decision_basis` | object | 第 2 轮起必填；保存截至上一轮的完整评分、PRF 判定和既定下一步 |
| `limits.max_cards_per_path` | integer | 1-30，默认 30；每路首屏最多抽取的卡片数 |
| `limits.primary_max_details` | integer | 0-5，默认 5 |
| `limits.secondary_max_details` | integer | 0-3，默认 3；没有第二路时视为 0 |
| `action_delay_ms` | integer | 800-5000，默认 1200；作为普通操作延迟基准，Builder 生成 ±20% 的浮动值，不由 Agent 逐步等待 |

每路固定只采首屏。search 返回卡片后，Agent 按已看台账和两路名单去重，再调用 collect。

`semantic_criteria` 只接受：

- `must_have`：必须满足，最多 20 条
- `nice_to_have`：加分项，最多 20 条
- `exclude_signals`：排除信号，最多 20 条

`decision_basis` 的字段与示例以 Builder 校验为准：`requirement_version`、`completed_iteration`、`candidate_scores`、`prf_decision`、`next_action`。同一需求版本的 `hard_filters` 与 `semantic_criteria` 必须保持一致；只换关键词不能同步改写条件。每条候选人评分保留 candidate_ref、真实 detail_ref、详情分区、首次评分轮次、三维原始分、matches、must_unknown、unknown 和证据说明。纠错或需求版本变化时写 correction_reason，但不改首次评分轮次，也不删除历史候选人。

Builder 会把本轮输入计划写入受工作流摘要保护的 `input_plan`。下一轮及 settle 从已完成工作流恢复真实执行计划；旧 iteration 文件即使被修改，也不作为绕过一致性校验的依据。

## 站内筛选字段

`site_filters` 支持：

- `current_cities`、`expected_cities`: 最多 9 个城市名称或标准编码。
- `experience_years`: 仅支持 `{min:0,max:0}`、`{min:1,max:3}`、`{min:3,max:5}`、`{min:5,max:10}`、`{min:10,max:null}`。
- `education`: 猎聘每个选项只含这一档。确认稿里的学历是下限，站内和硬筛分开写：
  - 下限是高中及以下、中专/中技、大专或本科：`site_filters` 省略 education，页面留在不限。`hard_filters.education` 写下限及其以上每一档。本科时为 `["本科", "硕士", "博士/博士后"]`；大专时再加大专；更低的下限把该档到博士/博士后都写上。
  - 下限是硕士：`site_filters.education` 与 `hard_filters.education` 都写 `["硕士", "博士/博士后"]`。页面点「硕士」和「博士/博士后」。
  - 下限是博士：两边都只写 `["博士/博士后"]`。
  - 用户写明只要某一档时，两边都只写那一档。
  - 站内最多两个值。可用值：本科、硕士、博士/博士后、大专、中专/中技、高中及以下。
- `school_requirements`: 最多一个值，支持 `211`、`985`、`double_first_class`、`overseas`。
- `company`: 最多一个公司名称的字符串数组，例如 `["字节"]`。只使用用户已确认的名称；多公司 OR 名单保留在 `hard_filters.company`，不要擅自挑第一家公司缩小召回。
- `activity_recency`、`job_hop_frequency`: 单个预设字符串，见下方映射；只在用户明确指定时填写，未指定或不限时省略。
- `age_range`: `{min,max}` 整数对象，边界为 16–60，至少给一个边界；仅用于站内筛选，不得写入 `hard_filters`。
- `gender`: 单个值，支持 `male`、`female`、`男`、`女`；仅用于站内筛选，不得写入 `hard_filters`。

策略允许写入但页面没有控件的字段：

- `work_content`: 写入 `site_filters` 时 Builder 会记 `SITE_FILTER_UNSUPPORTED` 并跳过页面筛选；请同时写入 `hard_filters` 做文本硬筛。

年龄、性别、活跃度、跳槽频率只用于站内缩小召回，不参与硬筛、评分或排序。这四项没有本地硬筛回退；页面操作失败时按 `unsupported_filters` 报告未验证，不得当作已满足。

站内筛选只能使用猎聘支持的离散预设。Selector、控件定位、弹窗交互和取值标签由 Skill 渠道资产维护，计划中不得出现 Selector 或点击步骤。不要为了表达 `0-3 年` 等精确范围而选近似预设；把精确条件保留在 `hard_filters`。若站内工作年限不是受支持的预设，Builder 只会在 `hard_filters` 存在完全相同范围时移除该站内条件并返回 warning，否则拒绝计划。

所有站内筛选都采用“失败后继续并上报”：某个字段的页面操作失败时跳过该字段、继续关键词搜索，并把字段、请求值和错误原因写入对应路径的 `search.<path>.unsupported_filters`。站内筛选只是缩小召回范围；同字段若属于硬条件，仍由后续卡片和详情 `data.filter` 执行。活跃度、跳槽频率、年龄、性别没有本地硬筛回退，失败记录的 `context.hard_filter_fallback` 为 false，必须说明条件未验证。

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

两项都是点选即提交的下拉筛选。Builder 在点击前校验筛选行、触发器、浮层和候选项均为唯一目标；点击后检查下拉收起、框内回显、已提交筛选标签和结果加载结束。人数不变或零结果都是有效表现。

### 公司名称筛选

公司名称使用行内联想输入。Builder 在“公司名称”筛选行内定位唯一 combobox，读取当前控件的 `aria-controls`（兼容 `aria-owns`），只在关联浮层内选择文本完全相同的唯一候选，再确认框内已选、点击行内确定并校验已提交筛选标签。不得固化 `#rc_select_x`、按视觉顺序猜控件或全页点击同名文本。

`site_filters.company` 最多一个值。用户要求多家公司任一背景时，完整名单写入 `hard_filters.company` 并省略站内公司条件；只有明确限定单一公司时才缩小页面范围。

## 硬性过滤字段

`hard_filters` 支持：

- `current_cities`、`expected_cities`、`education`: 字符串数组。
- `experience_years`: `{min,max}`。
- `school_requirements`: 字符串数组，支持 `211`、`985`、`double_first_class`、`overseas`；数组内按“满足任一项”判断。
- `company`、`work_content`: 字符串数组；卡片阶段缺失或未命中记 unknown，详情阶段未命中记不符合。
- `required_keywords.all`: 必须全部命中的关键词数组。
- `required_keywords.any`: 至少命中一个的关键词数组。
- `required_keyword_groups`: 二维字符串数组。组与组之间是 AND，每组内部是 OR。

search 执行两路查询、站内筛选和卡片硬筛后返回，不打开详情；collect 只采集 Agent 选定的人，再做详情硬筛。两次执行同属一轮，评分与 Controller 仍各做一次。

卡片上能够明确读到的城市、学历、工作年限等字段可以直接淘汰不符合者。列表摘要没有出现关键词、院校标签或其他可能被页面折叠的信息时只记为 `unknown`，不得提前淘汰。Builder 为卡片和详情分别生成声明式谓词；通用浏览器不理解招聘字段。

用户或 JD 明确声明为硬性的站内条件必须同步写入 `hard_filters`。不要假设站内筛选等同于最终硬筛。

## 补搜计划

门槛和先采再补见 SKILL.md 步骤 9。此处只规定字段。计划文件固定为：

```text
<TASK_WORK_DIR>/wts/search-plans/iteration-N-refill.json
```

编译：

```
python "/ABSOLUTE/BUILTIN_SKILLS_DIR/wts/scripts/build_workflow.py" refill --task-id TASK_ID --iteration N --task-work-dir "/ABSOLUTE/TASK_WORK_DIR" --plan-file "/ABSOLUTE/TASK_WORK_DIR/wts/search-plans/iteration-N-refill.json"
```

只填一个字段，其余从本轮已执行的 search 计划抄：

```json
{ "dropped_company": "实在智能" }
```

Builder 校验：本轮已有 search 卡片结果；可采人数大于 0 时必须已经采集过；可采人数已达主路径上限则拒绝；`dropped_company` 是原 `primary_query` 里的一个完整词，且不在 `hard_filters.company`；新查询 = 去掉该词后的主路径，长度仍 1–50；只编主路径、只出卡片；同一轮只能一次。`executed_plan` 跳过补搜工作流，下一轮仍对账原计划的硬条件。

第二次采集路径：`<TASK_WORK_DIR>/wts/search-plans/iteration-N-refill-collect.json`，命令仍是 `collect --iteration N`。只填 `result_ref` 和 `primary`；`result_ref` 必须是这次补搜的卡片结果。名单长度不得超过「主路径上限 − 本轮主路径已采集数」。

```
python "/ABSOLUTE/BUILTIN_SKILLS_DIR/wts/scripts/build_workflow.py" collect --task-id TASK_ID --iteration N --task-work-dir "/ABSOLUTE/TASK_WORK_DIR" --plan-file "/ABSOLUTE/TASK_WORK_DIR/wts/search-plans/iteration-N-refill-collect.json"
```

扩张的 `query` 除了本轮 `primary_query` / `secondary_query`，也可以是补搜后的主路径查询。

## 常规详情名单

路径：`<TASK_WORK_DIR>/wts/search-plans/iteration-N-collect.json`，命令为 `collect --iteration N`。只填以下字段，不重写搜索条件。第 1 轮及没有第二路时只写 `primary`：

```json
{
  "result_ref": "result://TASK_ID/<本轮卡片结果摘要>",
  "primary": ["liepin:a1b2c3d4e5"]
}
```

第 2 轮起有第二路时才写 `secondary`；无人可选写 []：

```json
{
  "result_ref": "result://TASK_ID/<本轮卡片结果摘要>",
  "primary": ["liepin:a1b2c3d4e5"],
  "secondary": []
}
```

没有第二路时多写 `"secondary": []` 与省略同等。本轮存在的路径必须填写。主路径最多 5 人、第二路最多 3 人，且不超过本轮计划上限；只选相应卡片结果中 matched/unknown 的编号，两路不重复。Builder 从结果恢复原计划，拒绝越界名单。collect 返回 `details.primary/secondary` 和 `failures.primary/secondary`；评分的 detail_ref 引用这次结果。

## 扩张计划

触发与挑人见 `seen-and-expand.md`。此处只规定字段。计划文件固定为：

```text
<TASK_WORK_DIR>/wts/search-plans/iteration-N-expand-K.json
```

N 是当前轮次，K 是本轮第几次扩张（1-3）。编译命令的 `workflow_type` 为 `expand`，带 `--iteration N --expansion K`。字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `requirement_version` | string | 与本轮 iteration-N.json 相同 |
| `query` | string | 必填；必须逐字等于本轮已执行的 `primary_query`、`secondary_query` 或补搜后的主路径查询，扩张只重开同一页 |
| `include_candidate_refs` | string[] | 必填，1-30 个、不重复；Agent 从该路 `candidates.<path>` 卡片里挑出要打开的人。Builder 编译为卡片谓词 `selected_for_expansion`：不在名单内即 reject；详情预算 = 名单长度 |
| `site_filters` | object | 照抄本轮计划 |
| `hard_filters` | object | 照抄本轮计划；与已执行计划不一致即拒绝编译 |
| `semantic_criteria` | object | 照抄本轮计划；与已执行计划不一致即拒绝编译 |
| `action_delay_ms` | integer | 同搜索计划 |

没有 `secondary_query`、`limits`、`decision_basis`。Builder 从 Workflow Store 找回本轮真实执行的计划做一致性校验，本轮没有已完成结果时拒绝编译。扩张工作流的 `iteration` 仍是 N，但带 `expansion=K` 标记，下一轮和 settle 找回本轮计划时会跳过它。

```json
{
  "requirement_version": "v1",
  "query": "AI Agent LangGraph RAG 阿里巴巴",
  "include_candidate_refs": ["liepin:a1b2c3d4e5", "liepin:f6g7h8i9j0"],
  "site_filters": {"expected_cities": ["上海"]},
  "hard_filters": {"expected_cities": ["上海"], "required_keyword_groups": [["AI Agent"]]},
  "semantic_criteria": {"must_have": ["有大模型应用或 Agent 落地经历"], "nice_to_have": [], "exclude_signals": []}
}
```

结果只有一个分区 `expand`：`summary.paths.expand`、`search.expand`、`candidates.expand`、`details.expand`、`failures.expand`；`summary.workflow` 为 `candidate_expand`。评分条目的 `detail_section` 写 `details.expand`，`scored_iteration` 写 N。

## 结果分区

工作流按路径落盘，不要把两路结果混成一个无标记列表：

- `summary.paths.primary` / `summary.paths.secondary`
- `search.primary` / `search.secondary`
- `candidates.primary` / `candidates.secondary`
- `details.primary` / `details.secondary`
- `failures.primary` / `failures.secondary`

卡片和详情会带 `search_path=primary|secondary`。没有第二路时，不要读 `secondary` 分区。

## 示例

第 1 轮只有主路径（主锚点 + 2 支持词 + 公司词）：

```json
{
  "primary_query": "AI Agent LangGraph RAG 阿里巴巴",
  "site_filters": {
    "expected_cities": ["上海"]
  },
  "hard_filters": {
    "expected_cities": ["上海"],
    "education": ["本科", "硕士", "博士/博士后"],
    "required_keyword_groups": [["AI Agent"], ["LangGraph", "LangChain"]]
  },
  "semantic_criteria": {
    "must_have": ["有大模型应用或 Agent 落地经历"],
    "nice_to_have": ["熟悉 RAG"],
    "exclude_signals": ["纯销售岗"]
  }
}
```

第 2 轮主路径（第 1 轮召回少，Agent 减到 1 支持词并换公司词）+ 第二路：

```json
{
  "primary_query": "AI Agent LangGraph 字节跳动",
  "secondary_query": "AI Agent RAG",
  "site_filters": {
    "expected_cities": ["上海"]
  },
  "hard_filters": {
    "expected_cities": ["上海"]
  },
  "semantic_criteria": {
    "must_have": ["有大模型应用或 Agent 落地经历"],
    "nice_to_have": ["熟悉 RAG"],
    "exclude_signals": ["纯销售岗"]
  }
}
```
