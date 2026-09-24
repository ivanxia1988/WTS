# 反思

主 Agent 在步骤 11 读。本步只有建议权：不晋升待试词、不改词表、不写查询。只用本轮回执、目标公司池、当前词表（活跃 / 备用 / 待试 / 已拒绝）和本轮 PRF 判定，不读简历。

## 写进决策记录

```
{
  "coverage": {"primary_new": 0, "secondary_new": 0, "refill_new": 0, "skipped_seen": 0},
  "support_words": [{"word": "", "action": "activate|keep|downweight|remove", "reason": ""}],
  "query_shape": {"primary_support_count": 1, "reason": ""},
  "next_company": {"name": null, "reason": ""},
  "stop_suggestion": {"stop": false, "reason": ""}
}
```

`coverage` 取自本轮各次回执的 `paths`：各路的 `eligible` 与 `skipped_seen`。

## 口径

- **支持词**：对照本轮各路的可评人数和新增可推荐，给现有活跃词和备用词激活 / 保留 / 降权 / 移除建议，各附一句依据。
- **查询形态**：检索是全部词都要命中，词越多召回越少。本轮主路径可评人数少于上限就建议下一轮减到 1 个支持词；可评人数多但可推荐占比低就建议保留 2 个支持词、换词族。
- **下一公司**：从目标公司池里状态为未用的公司提议下一轮公司词，或提议不带（`name` 为 null），附一句依据。已用和人不够的不再提议。
- **停止**：仍有未试的活跃词或备用词、且未成强池时，`stop_suggestion.stop` 为 false。

可以观察待试词，但晋升与造词是 PRF 的权限。

完成标准：对每个活跃词、查询形态、下一公司各有表态。
