# Domi 原子能力说明：供 Skill 编排使用

核对日期：2026-09-22。依据 Domi 当前客户端源码及本地 Root 工具注册整理，适用于普通 PC 的本地优先会话。具体工具是否可用，以当前运行时注入的工具清单、参数 schema 和后端启用配置为准。

导航：[运行模型](#运行模型) · [浏览器](#浏览器能力) · [联网](#联网查询) · [澄清](#用户澄清与确认) · [文件与执行](#文件文档与本地执行) · [本机简历检索](#本机简历检索) · [记忆与业务能力](#记忆子任务与云端业务能力) · [编排建议](#skill-编排建议) · [源码依据](#源码依据)

## 运行模型

```text
用户 → 本地 Root → Skill 的步骤与决策
                    ├─ 文件、文档、本地脚本
                    ├─ 本机简历索引检索（search_local_resumes）
                    ├─ Electron 内置浏览器 → 页面插件
                    ├─ 用户澄清卡片 → 暂停并恢复原任务
                    └─ 联网搜索 / 已启用的云端业务 Agent
```

Skill 提供领域规则、参数组织、流程与必要脚本；Domi 提供真实工具执行、身份隔离、任务状态和结果存储。本地优先不代表模型离线。IM、定时任务仍有云端链路，不能假定它们拥有同一套本地工具。

当前本地 Root 每批只允许一个工具调用，多个工具按顺序衔接；要减少网页动作之间的模型往返，使用一次 `browser_run_workflow` 编排连续动作，不依赖模型同时发起多项工具调用。

| 能力 | 主要入口 | 可用条件 |
| --- | --- | --- |
| 浏览器操作与工作流 | `browser_*` | 本地浏览器能力启用，Electron 与页面插件可用 |
| 联网检索 | `web_search` | 本地 Root、Domi 登录及云端搜索服务可用 |
| 用户澄清与确认 | `request_user_input` | Domi 的人机交互中间件与前端卡片 |
| 文件读写与搜索 | `ls/read_file/write_file/edit_file/glob/grep` | 当前工作区和文件权限允许 |
| 文档文本提取 | `extract_document_text` | 本地文件及对应解析依赖可用 |
| 本机简历检索 | `search_local_resumes` | 已在「整理简历」添加来源并完成索引；本地检索桥与登录会话可用 |
| 本地命令 | `execute` | 运行时启用了 Shell；使用其托管环境和权限 |
| 记忆 | `search_local_memory/expand_local_memory/save_user_profile` | 当前用户的本地记忆上下文可用 |
| 子任务 | `task` | 实际清单提供对应子 Agent；子 Agent 工具不一定与 Root 相同 |
| 招聘业务 | 已启用的云端 Agent 工具 | 后端当前配置及账号权限允许 |

## 浏览器能力

### 1. Agent 直接可调用的工具

| 工具 | 用途 | 主要输入及结果 |
| --- | --- | --- |
| `browser_embedded_status` | 查看宿主、插件、传输、页面与人工等待状态 | `inspect_page`；它不替代网站登录状态判断 |
| `browser_open` | 打开网页或本地文件 | `url`，可选 `tab_id/new_tab`；网页在内置浏览器打开，本地绝对路径或 `file://` 交给系统默认应用 |
| `browser_tabs` | 管理当前会话标签页 | `action=list/new/switch/close`，可选 `tab_id/url`；列表包含页面及 iframe 标识 |
| `browser_observe` | 读取正文、可交互元素和 iframe | `tab_id/frame_id/target`；正文用 `offset/max_chars`，元素用 `element_offset/max_elements` 分页 |
| `browser_act` | 执行一个动作 | 统一的 `action`、定位与动作参数，见下表 |
| `browser_screenshot` | 截取当前标签页视口 | 可选 `tab_id`；返回图片及任务内的本地截图路径 |
| `browser_run_workflow` | 执行连续动作或编译流程 | `steps` 与 `workflow_ref` 二选一；返回状态、结果引用及相应进度/失败信息 |
| `browser_read_workflow_result` | 读取持久化结果 | `task_id/result_ref/section/offset/limit`；支持当前会话内相应任务的结果 |
| `browser_cancel` | 停止本任务的浏览器操作 | 不关闭登录会话，不自动重放动作 |

本地文件由系统打开后不会产生可继续观察或操作的浏览器标签页。文件内容应使用文件或文档工具读取。

### 2. 单步动作及定位

以下名称放在 `browser_act.action` 或普通工作流的步骤 `action` 中，**不是独立的 `browser_click/browser_type` 工具**。

| 动作组 | `action` | 常用参数 |
| --- | --- | --- |
| 页面与标签页 | `navigate/new_tab/list_tabs/switch_tab/close_tab/back/forward/reload` | `url`、`tab_id` |
| 读取与截图 | `snapshot/read/screenshot` | `target`、分页参数；截图以顶层视口为准 |
| 点击与输入 | `click/fill/press` | `target`；填写用 `value`，按键用 `key`，支持 `alt/ctrl/meta/shift` |
| 表单选择 | `select/check` | `value/values`、`checked` |
| 鼠标与滚动 | `hover/scroll` | `target` 或适用的坐标；`direction`、`distance` |
| 等待 | `wait` | 可指定目标 `state=visible/hidden` 和 `timeout_ms`；无目标时等待 DOM 稳定 |
| 人工交接 | `request_user_action/resume_user_action` | 请求时必填 `message`，可选 `tab_id` |

`target` 支持当前观察获得的 `ref`，或 `css/role/name/text/label/placeholder` 及必要的 `index`。`name/text` 按精确匹配理解；CSS 使用标准浏览器语法，不支持 Playwright 的 `:has-text` 等扩展。返回多个目标而无法确定时应重新观察。

元素 `ref` 只对当前文档有效；导航、目标替换后重新观察。页面查询可进入 open shadow roots；iframe 使用观察结果中的 `frame_id` 定向操作。顶层 `click/hover` 也可使用截图确认后的完整 `x/y`，但不能与 `target` 或 `frame_id` 混用。坐标不能从经验猜测。

示例：已观察确认当前页面存在唯一名为“搜索”的文本框后，填写并提交：

```json
{
  "steps": [
    {"action": "fill", "target": {"role": "textbox", "name": "搜索"}, "value": "${context.query}"},
    {"action": "press", "target": {"role": "textbox", "name": "搜索"}, "key": "Enter"},
    {"action": "wait"},
    {"action": "snapshot", "save_as": "results"}
  ],
  "variables": {"query": "招聘顾问"},
  "interaction_mode": "human"
}
```

这是 `browser_run_workflow` 的参数示例，定位名称必须来自目标页面。等待 DOM 稳定不保证后台检索已完成；知道结果容器时应优先等该容器的可见/隐藏状态。

### 3. 两种工作流

| 形式 | 适用场景 | 编排能力 |
| --- | --- | --- |
| `browser.actions.v1` | 普通、已经明确定位条件的动作序列 | 通过 `steps` 传入 1–50 步；使用与单步相同的动作结构、`variables`、`save_as` 和 `${context.variable}`；顺序执行，失败停止 |
| `browser.workflow.v1`，schema 2 | WTS 等稳定渠道流程 | Skill Builder 将页面规则编译成文件并返回 `workflow_ref`；支持条件、循环、结构化抽取、硬筛与详情遍历 |

两种入口互斥。模型不直接把第二种的整份 JSON 塞进工具参数；WTS 使用 [Builder](source/scripts/build_workflow.py) 输出的引用。

编译流程的声明式原子操作如下。它们是 Builder 可编排的协议字段，不是每个都单独注册成模型工具：

| 层级 | 原子操作 | 用途 |
| --- | --- | --- |
| 宿主 | `page.navigate`、`page.run` | 页面导航、运行页面程序 |
| 宿主 | `data.filter` | 按声明式谓词筛选已抽取数据 |
| 宿主 | `tabs.foreach` | 遍历已发现的详情目标，在标签页内采集并汇总 |
| 宿主 | `result.emit` | 输出结构化结果 |
| 页面 | `page.detect`、`page.wait` | 状态识别、登录/验证码检测、等待条件 |
| 页面 | `page.click/fill/press/scroll/hover` | 定位后的交互动作 |
| 页面 | `page.extract`、`page.extract_list` | 按 Schema 抽取对象或列表 |
| 页面 | `data.set`、`data.append` | 保存变量、积累结果 |
| 页面 | `flow.if/foreach/repeat/break` | 条件分支与有界循环 |

`data.filter` 当前支持 `text.includes_any`、`text.includes_all`、`text.includes_groups`、`number.in_range`、`set.intersects`。字段、缺失值策略、抽取 Schema、页面检测和筛选交互由 Skill 声明；网页动作只允许协议内的操作，不提供任意 JavaScript/evaluate 入口。

单步工具支持 `select/check/snapshot/read`，不代表编译流程 `page.run` 接受所有同名操作；以宿主的 `PAGE_OPERATIONS` 白名单为准。

### 4. direct 与 human

- 通用独立动作和普通动作序列默认 `direct`；指定 `interaction_mode="human"` 启用拟人交互，步骤的显式值优先于工作流默认值。
- `human` 提供网页内渐进鼠标移动、点击前检查位置和遮挡、短暂停顿、原生逐字输入与有界分段滚动；支持中文及 emoji，填写结束核对文本。它不移动系统鼠标、不要求抢占桌面焦点。
- 当前拟人填写最多 2000 个字符，受动作超时约束；长文本可显式选择 `direct`，不会悄悄降级。iframe 的元素点击仍使用原有 DOM 路径，原生下拉选择仍直接选择选项。
- WTS 渠道配置默认 `human`。Builder 通过 `--interaction-mode` 选择并固化模式，加入 `interaction.human.v1` 能力要求；执行 `workflow_ref` 时不能覆盖。
- 页面跳转、目标替换、焦点丢失、超时或人工接管导致输入中断时停止，部分输入不当成完成，也不自动重输。拟人操作不保证避免风控。

### 5. 登录、人工接管与取消

网页登录状态按 Domi 账号和服务环境隔离并持久化；标签页按会话归属。同一账号的新对话可复用有效登录，站点令登录失效时仍需重新登录。一个宿主同时只执行一个浏览器操作。

普通工具识别到登录或验证码后，调用：

```json
{"action":"request_user_action","message":"请在浏览器中完成登录，完成后告诉我继续。"}
```

人工等待会保留页面，即使当前工具或聊天轮次结束。等待期间可以观察和截图；用户明确完成并要求继续后，用 `resume_user_action` 解除等待，再观察页面确认实际状态。编译流程则按 `page.detect` 等既定恢复条件处理。

用户主动接管或手动导航会停止相应自动操作；普通主动接管后，本轮不再继续自动输入，新用户轮次才重新允许。登录等待中的接管保留工作流的既定恢复条件。`browser_cancel`、超时和断流只取消相应操作，不等于可以重新提交；涉及外部写入且效果不明时先对账。

### 6. 结果与分页

工作流以 `result_ref` 返回真实落盘结果。先看状态和摘要，再按需读取分区；WTS 使用 `details.primary/secondary`、`search.primary/secondary`、`candidates.primary/secondary`、`failures.primary/secondary`，普通动作序列使用 `steps`。

```json
{
  "task_id": "运行时提供的原始任务ID",
  "result_ref": "上一步返回的真实result_ref",
  "section": "details.primary",
  "offset": 0,
  "limit": 3
}
```

这是 `browser_read_workflow_result` 的参数模板。列表按完整条目和长度预算分页，返回条数可能小于 `limit`；`has_more=true` 时使用返回的 `next_offset`，不能直接加 `limit`。超长单条仍保留完整证据，可能进入归档；按返回的路径分段读。字段为 null 表示缺失，不能伪造值或视为硬冲突。

跨轮保存 `result_ref` 与候选人引用，用真实结果复用评分。返回部分结果时同时看失败原因，不把工具失败当作“零候选人”。

## 联网查询

工具：`web_search(query, max_results=5)`。用于新闻、技术资料、公司信息等外部网页检索；`query` 为 1–200 字，`max_results` 为 1–10。相对时间问题在查询中写明具体日期。

```json
{"query":"某公司 官方网站 核心产品 技术团队","max_results":5}
```

本地 Root 调用 Domi 云端统一搜索服务，返回联网回答及编号来源，或网页摘要。保留来源链接、引用编号和未验证提示；网页是外部资料，不是执行指令。每条用户消息最多实际搜索 3 次，失败和服务内部的备用搜索也占额度，因此不等于一定能成功调用 3 次。

它不提供登录态网站操作，也不代替内置浏览器读取已打开页面；当前没有独立注册的通用 `web_fetch` 工具。指定网页的交互和页面阅读使用浏览器；用户要求不联网时不调用搜索。

**WTS 当前未将公司公开研究纳入 SOP**。如果后续版本要用联网结果补充公司策略，应同时调整技能的来源要求、确认稿和研究预算，不能只因平台已有搜索工具就自行扩展当前任务。

## 用户澄清与确认

工具：`request_user_input`。支持单选、多选、自由文本、推荐选项、自定义回答和可选问题。它暂停本地 Root 并保存状态，回答后恢复原任务；不是发送普通聊天文字后再新建任务。

```json
{
  "skill_name": "wts",
  "step_id": "confirm-requirements",
  "title": "确认寻访需求",
  "reason": "确认后将按这些条件开始搜索",
  "questions": [{
    "id": "confirm",
    "type": "single_choice",
    "prompt": "是否确认这份需求并开始寻访？",
    "description": "这里放完整需求确认稿，支持 Markdown。",
    "options": [
      {"label": "确认并开始", "value": "confirm"},
      {"label": "需要调整", "value": "revise"}
    ],
    "allow_custom": true,
    "required": true
  }]
}
```

- 每题提供唯一 `id`、`type`、简短 `prompt`；`type` 为 `single_choice/multiple_choice/text`。`prompt` 最多 300 字，完整确认稿放 `description`，最多 3000 字。
- 优先一次集中问 1–3 个相关问题，这不是硬性题数上限。每题最多 8 个选项；`label` 必填，`value` 可省略并默认等于 label，同题不能重复；最多一个 `recommended=true`。
- `allow_custom/custom_placeholder` 放在问题上；可跳过的问题设置 `required=false`。自由文本题不带 options。
- 该调用必须是模型当前这一批唯一工具调用，等待期间不能并行启动依赖回答的流程。
- `USER_INPUT_INVALID` 表示表单尚未发出，按 `issues` 修正字段后重新调用；保留待确认内容，不能把参数报错当成已获得确认。

网页登录接管用 `browser_act(request_user_action)`；业务需求澄清用 `request_user_input`，两者用途和恢复条件不同。

## 文件、文档与本地执行

### 文件工具

| 工具 | 用法要点 |
| --- | --- |
| `ls` | 列举已知目录 |
| `glob` | 按文件名模式查找 |
| `grep` | 搜索文件中的字面文本，不按正则解释 |
| `read_file` | 文本按 `offset/limit` 读取，offset 从 0 开始；返回的行号不属于文件内容；媒体支持取决于工具、依赖与模型能力 |
| `write_file` | 新建文件，已有文件不能靠重复写入覆盖 |
| `edit_file` | 对已读内容做精确替换；默认旧文本需唯一匹配，必要时显式使用 `replace_all` |
| `execute` | 运行本地脚本或命令，返回输出与退出码；仅在实际工具清单提供时使用 |

Skill 脚本适合确定性计算、结构转换、校验和报告数据整理。命令环境、超时、输出长度、依赖与写入边界由 Domi 运行时管理；不要另起 Chrome/Playwright 替换已提供的内置浏览器链路。

运行时提供原始任务 ID、技能绝对路径、任务工作目录和默认产物目录。Shell 可读取 `DEEPAGENT_TASK_WORK_DIR`、`DEEPAGENT_WORKFLOW_STORE_DIR`、`DEEPAGENT_BUILTIN_SKILLS_DIR`、`DEEPAGENT_OUTPUT_DIR` 等注入路径；任务 ID 使用上下文或 `DEEPAGENT_RUNTIME_TASK_ID` 中的实际值，不从哈希目录名猜测。计划和中间结果写任务目录，交付文件用运行时产物目录，内置技能源码按只读资源使用。

### 文档文本提取

`extract_document_text(file_path, max_chars=20000)` 支持 PDF、DOCX、XLSX/XLSM/XLTX/XLTM 的本地文本提取。任务附件传运行时的 `local_ref`（如 `attachment:1`）。旧 `.doc/.xls` 需要先转格式。

这是文本读取工具：PDF 当前使用文本层提取，不提供扫描件 OCR 保证；DOCX 提取段落，不能当作完整排版和复杂表格解析；Excel 读取缓存值，不能当成计算公式引擎。返回内容受长度上限约束。

用户明确要求阅读、总结本地文件时使用。以人找岗、推荐报告、接单推荐等云端任务由其工具解析附件，不先在本地把简历全文提取后重新拼进请求。

## 本机简历检索

工具：`search_local_resumes(keyword, match_mode, limit, offset, file_types, folder_path)`。经 Electron 注册的本机回环桥检索用户此前通过「整理简历」建立的本机索引，返回简历正文详情、文件路径与分页信息。

- `keyword`：1–8 个空格分隔的关键词，字面关键词检索，不支持自然语言条件或布尔表达式；`match_mode` 为 `all`（各词同时匹配，默认）或 `any`。
- `limit`：每页 1–20 条（默认 10）；`offset` 仅在确有需要且 `has_more=true` 时使用结果返回的 `next_offset` 翻页。
- `file_types`：可选 `pdf/doc/docx/xls/xlsx`，空列表搜索全部；Word 简历用 `doc/docx`，Excel 台账用 `xls/xlsx`。
- `folder_path`：可选的已索引根目录完整路径，必须来自用户或已有结果的 `root_path`，不猜测路径。

```json
{"keyword":"Python 上海","match_mode":"all","limit":10,"file_types":["pdf","docx"]}
```

这是 `search_local_resumes` 的参数模板。返回条目带 `resume_detail.units[].content` 等正文详情（PDF/Word 附页码，Excel 附工作表名和行号），可直接阅读，不必为了正文再次逐文件调用工具；只有详情缺失、`truncated=true` 或需要最新原文时才按 `file_path` 读取原文件。详情有返回长度上限，未返回的部分不能当作不存在。Excel 的 `matched_rows` 仅保证每行命中至少一个词，`preview_rows` 是未命中正文时的台账预览；逐行核对条件和列含义，不把不同候选人的信息合并。

边界与限制：

- 只查已建立的索引：不扫描新目录、不上传文件，也不是禾蛙云端人才库；结果只反映本机已整理的简历与 Excel 人才台账。
- 查询串行执行，两次查询开始间隔不少于 1 秒；避免重复相同查询、轮询和无目的地遍历全库，不通过子 Agent/Shell 绕过频率限制。
- 大库查询、索引正文读取及首次索引准备会消耗 CPU 和磁盘 I/O，可能耗时数秒或更久；遇到繁忙或超时不要立即重试。

失败时返回 `code`、`message`、`next_action` 和 `agent_guidance`，必须据此区分状态：`LIBRARY_NOT_CONFIGURED` 表示尚未添加简历来源——明确告知用户还没有可搜索的已整理简历，引导其点击左侧「整理简历」添加 PDF/Word 简历目录或 Excel 人才台账，等整理完成后再搜索，此时停止继续搜索；`SEARCH_SCOPE_NOT_CONFIGURED` 表示 `folder_path` 不是已添加的根目录，需核对路径；`RESUME_INDEXING`、`RESUME_INDEX_FAILED`、`RESUME_SOURCES_UNAVAILABLE`、`RESUME_INDEX_NOT_READY`、`NO_SEARCHABLE_RESUMES` 分别对应整理中、整理失败、来源失效、尚未完成整理与没有成功索引的文件，按 `next_action` 引导处理。`NO_MATCHES` 仅表示本次条件无匹配，不能说用户没整理简历；`search_performed=false` 表示尚未执行关键词检索；`coverage_warning` 非空时说明覆盖不完整；连接、超时和限频类错误不要连续重试。技术详情仅用于定位，不必原样堆给用户。

该工具与文件、脚本工具同属本地能力，供 Skill 编排本机人才检索类流程时使用；搜索结果同样受用户登录身份隔离。

## 记忆、子任务与云端业务能力

| 入口 | 当前用途及边界 |
| --- | --- |
| `search_local_memory(query, memory_types, limit)` | 语义查找当前用户 Daily/Monthly/Summary/Profile；长度预算可能漏掉较早记录，没找到不等于从未发生 |
| `expand_local_memory(memory_type, date)` | 按日期展开本地记忆，不接受任意文件路径 |
| `save_user_profile(section, content, evidence, action)` | 保存本人长期事实或偏好；必须引用本轮用户原话；一次寻访条件或候选人信息不作为顾问长期画像 |
| `task(description, subagent_type)` | 委派有独立上下文的短期任务，当前提供 `general-purpose`；主 Agent 整合其一次性返回；不假设子 Agent 继承全部 Root 能力 |

以下是通过工具调用的**云端业务 Agent**，内部会执行完整业务流程，不是本地浏览器原子动作：

| 工具名 | 能力 |
| --- | --- |
| `job_search_agent` | 找职位 |
| `people_to_job_agent` | 以人找岗 |
| `job_analysis_expert` | 职位分析 |
| `order_recommend_expert` | 接单推荐 |
| `candidate_manage_agent` | 人才管理 |
| `recommend_report_expert` | 推荐报告 |

可见性和调用说明由后端当前配置控制。通常传 `message`，新任务用 `mode=new`，续办用 `mode=continue` 和对应 `task_ref`；业务对象通过工具定义的 `input_refs` 等引用。具体附件、身份、远端线程由运行时处理，不在 Skill 内写死凭证或自造 ID。

工具额度、等待恢复和任务归属均由运行时维护；失败尝试也可能计入额度。当前本地主/子 Agent 已排除 `write_todos`，不要把它写成必需步骤。菜单中的简历索引、上传、岗位 CRUD 等桌面功能，也不能仅凭存在页面就假定有同名 Skill 工具。

## Skill 编排建议

1. 从实际工具清单选能力，读取必要的技能契约；将业务规则放在 Skill，页面执行留给底座。
2. 缺少会改变结果的决定时用澄清卡片，明确回答后继续原任务。
3. 陌生页面先观察，再用单步动作；定位与路径稳定后组合动作序列，重复渠道流程再做 Builder 编译。
4. 将已完成结果、评分和下一步决定写成可复用结构。写文件或编译成功本身不构成重新评分的证据。
5. 先消费工具状态与结果引用，按实际分页继续；参数问题修正输入，效果未知先对账，避免盲目重放。
6. 对用户说明当前进展、等待原因和最终交付；用真实结果形成报告。不要承诺拟人操作能绕过风控，也不要把静态检查当作真实网站验证。

## 源码依据

以下路径相对 `hewa-domi-app/`，用于维护者后续核对；本文不复制宿主实现。本文覆盖的宿主代码以 2026-09-22 工作区为准；WTS 技能仓库最近提交为 `ee5675d`，其后的技能改动在本地完成、尚未提交，快照见 `source/`。本机简历检索工具对应提交 `4a0a1140`。

| 主题 | 源码入口 |
| --- | --- |
| Root 工具注册与功能开关 | `python/deepagent_server.py` |
| 浏览器工具与参数结构 | `python/tools/browser.py` |
| 宿主工作流白名单与执行 | `electron/service/embeddedBrowser/browserWorkflowRunner.js` |
| 基础动作、原生输入与人工接管 | `electron/service/embeddedBrowser/browserActions.js`、`browserInput.js`、`browserHost.js` |
| 页面插件协议与动作 | `browser-extension/embedded-workflow/protocol.js`、`content.js` |
| 结果存储与分页 | `python/tools/workflow_store.py` |
| 联网搜索与额度 | `python/deepagent_runtime_support/web_search.py` |
| 澄清表单与本地恢复 | `python/tools/user_input.py`、`python/deepagent_runtime_support/user_input_contract.py`、`local_user_input.py` |
| 文件与命令约定 | `python/deepagent_runtime_support/harness_prompts.py`、`config.py`、`workspace.py` |
| 文档提取 | `python/tools/document_extract.py` |
| 本机简历检索工具与检索桥 | `python/deepagent_runtime_support/local_resume_search.py`、`electron/service/resumeScanner/agentSearchBridge.js`、`agentSearchDetails.js`、`queryWorker.js` |
| 记忆工具与云端业务调用 | `python/deepagent_runtime_support/memory_tools.py`、`cloud_tools.py` |
| 跨端机器契约 | `contracts/domi-local-first-v1.contract.json` |

页面录制回放目前没有工具入口；不提供任意桌面 App 操作、任意网页 JavaScript 执行或验证码自动绕过能力。引入新工具需同时核对模型入口、执行端与契约，不能只修改 Skill 文案。
