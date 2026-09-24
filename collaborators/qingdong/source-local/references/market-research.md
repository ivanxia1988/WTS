# 市场求证

主 Agent 在步骤 13 写市场观察之前读。用网络搜索核对这次本地库样本，不改本地库的人数和分数。

## 输入

当前需求文件、`final-report-data.json`、步骤 4 的岗位定位和公司类别（没有则说明未做）。只用 settle 结果里的 `card`、`evidence_summary` 和人数，不读简历原文。

## 搜索

最多 6 次 `web_search`，每次 `max_results` 为 10。预算用完就用已有材料收尾。搜公开 JD、行业介绍和招聘报道，核对三件事：这类岗位常见技能和年限、常见雇主类型、这次样本里少见的要求在公开市场上是否常见。候选人个人和具体人名不搜。

## 结论

写进决策记录，供 `references/final-report.md` 的市场洞察使用：

```
{
  "skills": {"local": "", "public": "", "sources": [{"title": "", "url": ""}]},
  "profile": {"local": "", "public": "", "sources": [{"title": "", "url": ""}]},
  "company_sources": {"local": "", "public": "", "sources": [{"title": "", "url": ""}]}
}
```

`local` 只转述 settle 结果里已有的本次结果，人数不够写归纳时写「这次样本不足」。`public` 只写搜到的公开资料，每条判断至少有一个 `sources` 链接。没搜到就写「公开资料不足」，`sources` 为 `[]`。性别、学校名称、民族、婚育不写入。

完成标准：三小节各有 `local` 和 `public`，`public` 的每条判断都带来源或写明「公开资料不足」。
