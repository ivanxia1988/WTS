# guanfeng · Domi 内置 WTS Skill

这里交付 Domi 当前使用的「猎聘智能寻访」技能。它把 JD 转成经用户确认的需求，再编译浏览器工作流进行猎聘搜索、详情采集、候选人筛选与评分，最后交付带真实详情链接的寻访报告。

## 当前快照

| 项目 | 内容 |
| --- | --- |
| 同步日期 | 2026-09-22 |
| 源码来源 | `hewa-domi-app/python/skills/wts/`（快照为 2026-09-22 Domi 运行目录最终版本，含尚未提交到仓库的改动） |
| 技能身份 | `wts` / 猎聘智能寻访 / `$wts` |
| Builder 声明版本 | `0.5.2` |
| 渠道规则版本 | `liepin-2026.09.22.2` |
| 浏览器工作流 | `browser.workflow.v1`，`schema_version=2` |
| 默认交互模式 | `human`；支持显式切回 `direct` |

`source/` 直接是完整技能根目录，内容与上述最终版本一致；不额外套一层 `wts/`，也不带 Python 缓存或运行记录。仓库最近一次涉及 WTS 的提交为 `ee5675d`（2026-09-17），其后的技能改动尚未提交。`0.5.2` 是现有代码中的版本标识，最新变化按日期记录在 [CHANGELOG.md](CHANGELOG.md)，不与本仓库的 `wts-v0-N` 冻结测试版本混用。

## 文件导航

```text
guanfeng/
├── README.md
├── CHANGELOG.md
├── DOMI_ATOMIC_CAPABILITIES.md
└── source/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/search-plan.md
    ├── scripts/
    │   ├── build_workflow.py
    │   └── decision_basis.py
    └── assets/
        ├── channel/       # 猎聘页面规则、筛选配置、卡片与详情抽取
        └── workflows/     # 登录前置、搜索、详情采集模板
```

- [SKILL.md](source/SKILL.md)：需求澄清、确认门、搜索策略、评分、PRF、停止条件与报告 SOP。
- [搜索计划契约](source/references/search-plan.md)：SearchPlan、评分依据、结果分区和最终结算格式。
- [Builder](source/scripts/build_workflow.py)：校验计划，编译不可变工作流，执行本地结算。
- [评分与决策校验](source/scripts/decision_basis.py)：校验详情引用和历史评分，确定性计算总分、人数和 Top 10。
- [Domi 原子能力说明](DOMI_ATOMIC_CAPABILITIES.md)：技能可使用的浏览器、联网搜索、澄清、文件、执行、本机简历检索及其他工具。

## 当前支持的能力

| 环节 | 能力与边界 |
| --- | --- |
| 需求澄清 | 从 JD 拆出岗位、技能、城市、公司方向等条件，用结构化卡片澄清；用户明确确认前不操作浏览器 |
| 搜索编排 | 最多 5 轮；首轮仅主路径，第 2 轮起可加探索路径；每路只采首屏、最多 30 张卡片，每轮主路径最多 3 份详情、第二路最多 2 份 |
| 拟人操作 | 默认启用渐进鼠标移动、短暂停顿、逐字输入、分段滚动；详情抽取前有限浏览；支持 `--interaction-mode direct` |
| 筛选 | 站内筛选（含公司联想输入、活跃度、跳槽频率、年龄、性别等页面预设）、卡片预筛、详情硬筛分层处理；站内筛选失败记录原因并继续，缺失信息保留为 unknown；活跃度、跳槽频率、年龄、性别没有本地硬筛回退，生效失败时向用户说明未验证 |
| 评分复用 | 按候选人引用去重，保存三维原始分、证据与首次评分轮次；Builder 计算总分与 Top 10，避免反复重算 |
| 搜索调整 | PRF 从工作或项目经历的真实引文提取待试词，先在第二路试用，再根据新增可推荐候选人等证据决定是否晋升 |
| 需求一致性 | 同版本硬条件和语义评分项保持一致；以已执行工作流内的计划快照校验后续轮次，换搜索词不等于换需求 |
| 最终交付 | `settle` 结算最后已完成轮次，生成 `final-report-data.json`，包含 Top 10 的真实链接、分数、证据与 unknown |

当前技能不做公开公司研究，目标公司取自 JD 或用户输入；确认稿中的「池子」暂不作为独立检索队列执行。候选人语义评分由 Root 完成，没有独立并发评分器。平台具备联网搜索和子任务能力，不表示 WTS 已启用这些策略；Domi 已提供本机简历检索工具 `search_local_resumes`（见 [原子能力说明](DOMI_ATOMIC_CAPABILITIES.md#本机简历检索)），WTS 当前 SOP 未调用，后续可由技能编排从本机已整理简历中取人、取文件。

## 运行与接入

本技能运行在 Domi 的本地优先链路：本地 Root 负责理解与编排，Builder 生成流程，Electron 内置浏览器和页面插件完成网页动作，结果保存在当前会话的 Workflow / Result Store。模型和部分平台能力仍使用云端。

需要配套 Domi 提供 `execute`、文件工具、`request_user_input`、内置浏览器工具，以及当前任务 ID、任务目录、技能目录和 Store 路径。默认拟人模式还要求宿主与插件都支持 `interaction.human.v1`；如要在技能内编排本机简历检索，宿主还需提供 `search_local_resumes` 及其本地检索桥。只复制技能不能为旧客户端补齐这些底座能力。

Builder 只有以下三个入口；参数中的绝对路径与任务 ID 使用运行时提供的值：

| 命令 | 用途 |
| --- | --- |
| `preflight --iteration 0` | 编译登录前置流程，再由 `browser_run_workflow` 执行 |
| `search --iteration N` | 读取本轮计划，校验评分依据并编译搜索流程；N 为 1–5 |
| `settle --iteration N` | 读取最后完成的计划与 `wts/final-decision.json`，生成报告数据，不新增搜索 |

具体命令与文件格式以 [SOP](source/SKILL.md) 和 [计划契约](source/references/search-plan.md) 为准。登录、验证码与风控提示由用户接管；拟人模式不保证免于站点风控。

## 协作与验证

本目录作为独立交付区供维护者评审，合并入口仍是仓库主 `source/`。发布为独立测试版本时，按仓库规则同步技能名称、界面身份、Builder 身份及任务路径；不要直接覆盖其他已安装版本。

后续修改在 [CHANGELOG.md](CHANGELOG.md) 顶部按日期追加能力变化、原因、底座依赖和需要关注的验证点。每轮同步的验证范围限于文件一致性与文档静态核对，不代表已执行真实网站任务、运行测试或构建客户端；交付内容不包含真实会话、候选人资料或登录数据。
