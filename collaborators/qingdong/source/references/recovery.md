# 按结果续跑

开始采集、补搜、扩张，或中断后继续时读。沿用已确认需求和轮次；依据已保存结果选择下一阶段。Agent 可自主决定恢复页面或重新搜索，理由一句话即可。

## 对账与选择

1. 调用 `browser_embedded_status`。有活动动作先等待/查询结果，确认空闲后才执行另一个浏览器工作流；超时不代表没有执行。
2. 对已有执行记录运行：

```bash
python "/ABSOLUTE/BUILTIN_SKILLS_DIR/wts/scripts/recovery.py" --task-id TASK_ID --iteration N
```

首次编译采集会自动对账。返回 `completed`（真实详情引用）、`remaining`、`failed`、`uncertain`、`already_scored`、`score_files`、`occupied`、`attempts` 和 `page_checks`，不返回履历全文。没有结果的已编译采集是效果不明，不当成未执行。

3. 按事实继续：
   - 已采集：复用 `completed` 的详情引用。已评分：从按时间排序的 `score_files` 的 output 复用原评分返回（同人取最后一次），沿用已有 decision_basis；仅对未评分者派子 Agent。
   - 明确未执行：沿用原采集名单重新编译，Builder 自动扣除已完成和效果不明者，只执行 `remaining`。
   - 明确失败：核对错误字段，修复后可追加 `--retry-candidate CANDIDATE_REF --recovery-reason "原因"`，仅放行指定失败者的重试，其他未执行者正常继续。
   - 效果不明：先查可用结果，仍不明就跳过并报告缺口，继续其他人；已有成功详情优先于失败记录。

同一会话切换任务 ID 时，卡片/详情引用保持原样，新工作流用当前 TASK_ID。对账、保存评分和依赖原轮次的 Builder 命令追加 `--source-task-id OLD_TASK_ID`；原结果须能在当前会话 Store 中核验。

## 页面检查与恢复

常规采集、补搜采集和扩张默认只检查列表、定位所选编号并采集。每次执行后检查 `search.<path>.collection_check`：

- `ready`：读取索引，接着处理剩余任务。
- `needs_restore`：本路径没有打开候选人。返回 expected/observed；缺少旧快照也走此分支。筛选标签顺序、URL 跟踪参数不会触发恢复，真实查询、筛选或页码差异才需判断。

Agent 判断恢复原查询合适时，在原 collect/expand 命令追加 `--restore-search --recovery-reason "原因"`；这只恢复页面，仍扣除已完成者。需调整查询时走现有 search/refill 入口，保留结果和台账。重复 search/refill 默认复用已有结果，确需重新搜索时追加 `--recovery-reason "原因"`。不能通过增加轮次或扩张编号绕过续跑去重。

候选人按编号在当前页重新定位，消失或不唯一记失败。恢复后仍沿用已选编号，不按旧位置点人或自动替补。

## 结果和预算

同一逻辑轮次汇总所有执行结果；续跑不新增轮次或扩张次数。`occupied` 按编号计名额：已采集、已尝试及效果不明都占用，明确未打开不占用；常规主路径与补搜共用已确认计划的主路径上限（默认 5 人），第二路沿用计划上限（默认 3 人），扩张沿用原上限。`attempts` 保留各次结果证据，同一个人重试不会掩盖操作次数；没有证据的打开次数记未知。

将本轮 `result_refs`（详情及失败结果）逐个作为 `--result-ref` 传给 `score_inputs.py`，一次汇总导出。脚本按编号合并索引，保留每人的原 `detail_ref`、`detail_section` 和 `opened_at`；主 Agent 用索引和对账回执记账，将未评分者的 `profile_path` 交给评分子 Agent。没有结果引用时直接记录缺口；效果不明者保留在对账记录，不伪造已打开台账。

每次评分返回后，将原 JSON 写入当前任务的 `wts/scoring/iteration-N.json`，立即保存可复用的评分：

```bash
python "/ABSOLUTE/BUILTIN_SKILLS_DIR/wts/scripts/recovery.py" --task-id TASK_ID --iteration N --record-scores "/ABSOLUTE/TASK_WORK_DIR/wts/scoring/iteration-N.json"
```

脚本校验真实详情引用、分数和需求版本，返回不可变的 `score_file`。复用的评分仍写入 decision_basis，Controller 照常复核。更改需求后按新版本重评，保存时追加 `--plan-file` 指向新版本搜索计划；同版本纠错记录 correction_reason。
