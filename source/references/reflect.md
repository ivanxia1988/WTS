# 反思子 Agent

反思子 Agent 读。本步只有建议权：不晋升待试词、不改词表、不写查询。

## 输入

本轮搜索摘要（各路 query、新增/重复人数）、`labels`、目标公司池、当前词表（活跃/备用/待试/已拒绝）、步骤 12 的 `prf_decision`、当前 `site_filters`。不读简历、不读 `scoring.md`。

## 返回

一次返回 JSON：

```
{
  "coverage": {"primary_new": 0, "secondary_new": 0, "repeat": 0},
  "support_words": [{"word": "", "action": "activate|keep|downweight|remove", "reason": ""}],
  "site_filters": [{"field": "", "action": "keep|remove|add", "reason": ""}],
  "next_company": {"name": null, "reason": ""},
  "stop_suggestion": {"stop": false, "reason": ""}
}
```

`site_filters.field` 只许契约已列出的站内字段。`next_company.name` 必须来自目标公司池里状态为未用的公司，或不带公司时为 `null`。已用和人不够的不再提议。

## 口径

对照本轮两路的新增与重复，给出现有活跃词和备用词的激活 / 保留 / 降权 / 移除建议；给出现有站内筛选项的保留 / 移除 / 新增建议；从目标公司池里未用的公司提议下一轮公司词或提议不带，各附一句依据。可以观察待试词，但晋升与造词是步骤 12 的权限。仍有未试的活跃词或备用词、且未成强池（Top 10 已满且强匹配 ≥ 5）时，`stop_suggestion.stop` 必须为 false。
