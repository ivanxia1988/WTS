# 检索计划契约

主 Agent 在步骤 6 写计划时读全文；检索子 Agent 硬筛时读「硬性过滤字段」一节。

计划文件是主 Agent 与检索子 Agent 之间的领域输入。第 N 轮计划的唯一合法路径：

```text
<TASK_WORK_DIR>/wts-local/search-plans/iteration-N.json
```

N 为 1–3。同一轮修正时原地覆盖同一个文件。`ledger.py check-plan` 拒绝未知字段、越界轮次、重复的词组合，以及同一需求版本下被改动的条件。

第 1 轮只能有主路径。第 2 轮起可以增加第二路；两路查询不能相同。

## 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `requirement_version` | string | 当前已确认需求版本，如 `v1`；同版本条件保持一致 |
| `primary` | object | 必填。`{keywords, company}`：`keywords` 是 1–8 个不含空格的词，包含主锚点拆出的每个词；`company` 是其中那个公司词，不带公司词时为 `null` |
| `secondary` | object | 可选，第 1 轮禁止。`{keywords, kind}`：`keywords` 只含锚点和支持词；`kind` 为 `prf`（PRF 探针）或 `explore`（通用探索） |
| `hard_filters` | object | 见下文；子 Agent 对每份简历逐条判定 |
| `semantic_criteria` | object | `must_have` / `nice_to_have` / `exclude_signals` 三个数组，照录需求版本，各最多 20 条 |
| `limits.max_results_per_path` | integer | 1–30，默认 30；每路最多读取的检索结果条数 |
| `limits.primary_max_scored` | integer | 0–5，默认 5；主路径每轮最多评几人 |
| `limits.secondary_max_scored` | integer | 0–3，默认 3；第二路每轮最多评几人 |
| `file_types` | string[] | 可选，仅当用户限定了文件类型：简历文件 `["pdf","doc","docx"]`，Excel 台账 `["xls","xlsx"]` |
| `folder_path` | string | 可选，仅当用户给了目录；逐字照录用户输入，不自行推断 |

检索工具只支持一种组合方式：所有词都必须出现（`match_mode=all`）。计划里的一条查询就是一组都要命中的词，子 Agent 用空格把 `keywords` 连起来发出。同一词族的几种写法不能放进同一条查询；要试另一种写法，就在下一轮换词。

## 硬性过滤字段

`hard_filters` 支持：

| 字段 | 格式 | 判定 |
| --- | --- | --- |
| `cities` | 字符串数组 | 现居地或期望城市命中任一即符合；两者都写了且都不在内才淘汰 |
| `education` | 字符串数组，取值：博士、硕士、本科、大专、中专/中技、高中及以下 | 最高学历在数组内即符合。确认稿写下限时，数组写下限及其以上每一档（本科 → `["本科","硕士","博士"]`）；用户写明只要某一档时只写那一档 |
| `experience_years` | `{min, max}`，任一端可为 `null` | 按工作经历起止时间累计，重叠时段只计一次；不用年龄或毕业年份反推 |
| `company` | 字符串数组 | 当前或过往任一段经历在其中即符合 |
| `exclude_current_company` | 字符串数组 | 当前任职公司在其中即淘汰；曾经任职不淘汰。只放已确认的招聘公司 |
| `school_requirements` | 字符串数组，取值 `211`、`985`、`double_first_class`、`overseas` | 满足任一项即符合 |
| `work_content` | 字符串数组 | 工作或项目经历里出现任一项即符合 |
| `required_keywords.all` | 字符串数组 | 正文全部出现 |
| `required_keywords.any` | 字符串数组 | 正文至少出现一个 |
| `required_keyword_groups` | 二维字符串数组 | 组与组之间是 AND，每组内部是 OR |

每条硬筛只有三个结果：

- **matched**：每条都有正文证据满足。
- **unknown**：没有一条被正文明确抵触，但至少一条正文里没写。
- **rejected**：至少一条被正文明确抵触（写了上海，要求北京；写了大专，要求本科及以上）。

只有明确抵触才淘汰。检索结果被截断（`truncated=true`）或详情缺失时，先按 `file_path` 读原文再判；读完仍没写的条件记 unknown，不当作不具备。

不要写入年龄、活跃度、跳槽频率。年龄要求已按 SKILL.md 转成 `experience_years` 的，只写年限字段；跳槽频率留在排除信号里由评分处理。用户或 JD 明确为硬性的条件都要写进 `hard_filters`。

## 示例

第 1 轮只有主路径（主锚点 + 2 支持词 + 公司词）：

```json
{
  "requirement_version": "v1",
  "primary": {"keywords": ["Agent", "LangGraph", "RAG", "阿里巴巴"], "company": "阿里巴巴"},
  "hard_filters": {
    "cities": ["上海"],
    "education": ["本科", "硕士", "博士"],
    "required_keyword_groups": [["Agent"], ["LangGraph", "LangChain"]]
  },
  "semantic_criteria": {
    "must_have": ["有大模型应用或 Agent 落地经历"],
    "nice_to_have": ["熟悉 RAG"],
    "exclude_signals": ["纯销售岗"]
  }
}
```

第 2 轮主路径（第 1 轮召回少，减到 1 支持词并换公司词）+ 第二路：

```json
{
  "requirement_version": "v1",
  "primary": {"keywords": ["Agent", "LangGraph", "字节跳动"], "company": "字节跳动"},
  "secondary": {"keywords": ["Agent", "RAG"], "kind": "explore"},
  "hard_filters": {
    "cities": ["上海"],
    "education": ["本科", "硕士", "博士"],
    "required_keyword_groups": [["Agent"], ["LangGraph", "LangChain"]]
  },
  "semantic_criteria": {
    "must_have": ["有大模型应用或 Agent 落地经历"],
    "nice_to_have": ["熟悉 RAG"],
    "exclude_signals": ["纯销售岗"]
  }
}
```
