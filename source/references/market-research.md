# 市场求证子 Agent

市场求证子 Agent 读。在终态报告的市场观察写完之前，用网络搜索核对这次猎聘样本，不改猎聘上的人数和分数。

## 输入

当前需求文件、`final-report-data.json`、步骤 3.5 的岗位定位和公司类别（没有则说明未做）。不读简历全文，不读 `scoring.md`。

## 搜索

最多 6 次 `web_search`，每次 `max_results` 为 10。预算用完就用已有材料收尾。搜公开 JD、行业介绍和招聘报道，核对三件事：这类岗位常见技能和年限、常见雇主类型、这次样本里少见的要求在公开市场上是否常见。候选人个人和具体人名不搜。

## 返回

一次返回 JSON：

```
{
  "skills": {"liepin": "", "public": "", "sources": [{"title": "", "url": ""}]},
  "profile": {"liepin": "", "public": "", "sources": [{"title": "", "url": ""}]},
  "company_sources": {"liepin": "", "public": "", "sources": [{"title": "", "url": ""}]}
}
```

`liepin` 只转述输入里已有的本次结果，人数不够写归纳时写「这次样本不足」。`public` 只写搜到的公开资料，每条判断至少有一个 `sources` 链接。没搜到就写「公开资料不足」，`sources` 为 `[]`。性别、学校名称、民族、婚育不写入。
