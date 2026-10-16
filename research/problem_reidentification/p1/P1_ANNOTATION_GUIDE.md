# P1 独立人工标注指南

目标是在记录支持多条知识时判断是否存在可辩护的优先关系，不是完成一份必须选出第一名的推荐列表。允许并列、不足以比较和信息不足。先独立判断，再由第三人处理分歧。不要查看另一名评审、旧实验标签或整个仓库。

## 1. 阅读记录

卡片第 1–28 天为基线，第 29–42 天为当前窗。判断时点是第 42 天末。`weekday` 的 1–7 指周一至周日；不等于上班/休息日。`context.population` 是论文报告的成年人群范围，不是个体年龄。

`sleep_minutes` 是源设备估计的主睡眠时间；`time_in_bed_minutes` 是源日志的在床字段，不互相替代。`sleep_start_day_offset` 表示入睡相对于睡眠归属日的偏移。钟点没有可靠时区/DST 信息。活动和 sedentary 字段均为 Fitbit 自身分类，不据此推断强度、姿态、佩戴完整性、连续久坐或病因。RHR 不等于睡眠心率。零值只是源记录的零值。

null 是未知。`sleep_log_type` 和 `sleep_info_code` 为原始设备日志类型和状态字段，未翻译为临床质量结论；classic 日志不能证明存在 Light/Deep/REM 分期，非零 infoCode 单独标记为待核实。源 RHR=0 保留原值并明确标记为不能作生理解释，不代表真实零心跳。`quality_flags` 中重复标记表示同 logId 及全部选用睡眠字段一致的重复导出已折叠；冲突标记表示该日主睡眠无法无歧义选定，睡眠字段已保留为未知。未提供症状、诊断、药物、目标、偏好和自报告；不能将未知视为“没有”。

## 2. 各候选适用性：三选一

| 值 | 含义 |
| --- | --- |
| `applicable` | 知识核心适用条件受实际记录/已提供背景支持，有具体教育或解释价值。仍不表示必须优先推荐。 |
| `not_applicable` | 记录明确不满足条件，或该候选不能针对已观测事实提供具体价值；必须解释不匹配点。 |
| `insufficient_information` | 缺少可能改变适用性判断的必要信息，无法判断；不能改填“不适用”。 |

每条填写 `observations`、`conditions`、`rationale` 和 `missing_information`。可引用 `d29.sleep_minutes`、`d31.resting_heart_rate_bpm`、`context.population` 等；不可引用不存在或 null 的字段。适用判断至少有一条非空的具体观测。缺信息判断可没有已知观测，但必须填缺失类型并解释哪项条件无法判定。`conditions` 使用卡片逐条列出的 `C1.observable_conditions.0`、`C1.required_context.0`、`C1.population.0`、`C1.non_applicable_conditions.0` 或 `C1.support.0`。只引用条件编号不能替代文字解释。

通用健康知识并非自动适用；小幅个人变化不证明疾病。某候选有可靠出处，也不意味着它针对该案例适用。需要症状、真实强度或工作情境的条件不得补想。发现来源与正文范围不符，记录 `source_scope` 并说明，不通过调整标签掩盖。

## 3. 适用候选的逐对比较

对所有 `applicable` 候选的每一对填写一条 `comparisons`；例如三个适用候选就有三对。不要比较“不适用”或“适用性信息不足”的候选。

| relation | 含义 |
| --- | --- |
| `left_preferred` | 根据实际观测和两条知识的条件，可以解释左侧为何应先于右侧。 |
| `right_preferred` | 右侧有可辩护的优先理由。 |
| `tie` | 两条均适用且有积极理由认为在当前证据和目标下同等优先。不是“不知道选谁”。 |
| `incomparable` | 两条均适用，但现有判断维度之间没有可辩护的共同排序；不能认为同等优先。 |
| `insufficient_information` | 缺少一项可能改变相对优先级的信息；明确它是什么以及如何影响比较。 |

不要默认更严重的词、更长文本、更具体的条目、自己偏好的主题、候选顺序或更大的数值偏差应先推送。比较标准可涉及记录覆盖的直接性、当下持续性、已知目标等，但必须说明标准及记录依据；不同评审可能采用不同标准，这本身是需记录的分歧。不得从穿戴值虚构紧急性或疾病。

每对填写 `left`、`right`、`relation`、`observations`、`conditions`、`rationale`、`missing_information`。条件引用须同时覆盖左右候选。明确优先和并列至少引用一条实际观测。偏好不能成环，并列需传递；A 高于 B 且 B 高于 C 时不能将 A/C 标为并列或未知。

## 4. Case 决策

`decision.priority`：

- `clear`：至少两个明确适用候选，所有对都能判断为严格优先或并列，且至少一对有严格优先。
- `partial`：有严格优先，但部分对不可比较或缺信息。
- `none`：无严格优先，所有对为合理并列或不可比较；二者在原始比较中分别保留。
- `insufficient_information`：没有严格优先，且至少一对因缺信息不能比较。
- `not_comparable`：明确适用候选少于两个。

`decision.top_outcome` 与 `best_set`：

- `unique_best`：一个候选明确优于每个其他适用候选，且其他候选适用性均已判定；best_set 仅此一个。
- `tied_best`：两个或更多候选相互合理并列，并明确优于其余适用候选；可以全体并列。其他候选适用性均已判定。best_set 记录整个并列集合。
- `undetermined`：适用性已判定，但由于不可比较不能确定最优集合；best_set 留空。
- `insufficient_information`：缺信息可能改变面板最优集合，包括至少两个候选明确适用但还有候选适用性未知；best_set 留空。
- `not_comparable`：明确适用候选不足两个，不回答多候选优先级；best_set 留空。即使只剩一个适用，也不计为 P1 的“唯一最优”。是否因为其他候选信息不足会另外统计。

部分优先关系也可能有明确唯一最优（例如最优项优于其他所有项，但后两项不可比）。唯一最优与完全排序不是同一指标。全部并列可为 `priority=none, top_outcome=tied_best`。

决策仍须填写具体观测、知识条件、理由、`reason_codes` 和 `missing_information`。工具检查结构和逻辑，医学依据是否成立仍由人工审查。

缺失信息类型：`symptoms`, `diagnoses`, `medications`, `goals`, `preferences`, `age`, `work_schedule`, `wear_time`, `measurement_quality`, `activity_intensity`, `posture`, `sleep_experience`, `timezone`, `history`, `other`。`other` 必须在理由中展开。

理由类型：`applicability_condition`, `observation_interpretation`, `measurement_uncertainty`, `missing_context`, `priority_criterion`, `reasonable_tie`, `source_scope`, `other`。这些类型不是对错标签。

## 5. 提交和裁决

可以直接打开自己的 HTML 卡片，在页末离线表单中填写并导出每个 case 的 JSON；先选适用性，适用候选的比较表会自动出现。表单不联网提交、不自动保存，关闭前须导出。协调人用 `collect` 汇总同一评审的最终导出文件，再运行完整校验；不要把同一 case 的多个修订混在汇总文件夹中。

也可复制自己的 `annotations.template.jsonl` 到另一个文件编辑，不覆盖模板。每行一个 case；完成后 `status="complete"`, `human_attestation=true`，并填写带时区的 ISO `completed_at`。空白模板不是标签，不得提交 LLM 自动完成的表。

每人独立提交全部 case 后，由协调人运行校验和分歧队列生成。第三名人工 C 以 A 卡片的引用编号填写 `adjudications.template.jsonl`，查看 A/B 原始理由及双方卡片，确认 `reviewed_reviewers=["A","B"]`，在 decision.reason_codes 中记录实际分歧原因，并给出完整证据。不要为了结束争议强选一个第一名；信息不足可以是最终答案。

原记录不可回写。无分歧 case 沿用两人一致标签；有分歧 case 必须经过 C 才能进入全量最终比例。C 不能用一致意见覆盖原始一致率。
