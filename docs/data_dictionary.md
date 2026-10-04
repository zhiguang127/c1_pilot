# 数据契约与示例

## 1. Wearable case 的最终推荐 schema

结构以 [wearable_case.schema.json](../schemas/wearable_case.schema.json) 为准；JSONL 每行一个对象。语义约束仍需独立检查，JSON Schema 不证明统计正确、时间一致、设备真实性或健康事实正确。

| 字段 | 必需 / 单位 | 说明与可见性 |
| --- | --- | --- |
| schema_version | 必需，`1.0` | 数据契约版本；内部使用 |
| id | 必需，C001-C024 | 稳定关联键；模型不看 ID |
| case_type | 必需，四类枚举 | 分层评估标签；模型不看 |
| window_days / baseline_days | 必需，整数天 | pilot 为 14 / 28，连续日历跨度，不是非空值数；可给模型 |
| periods | 必需，date | 两段起止日期，闭区间；baseline 在 window 之前且不重叠 |
| observations | 必需 | 分别为 baseline_daily / window_daily；每天一行，连缺测日也保留；可给模型 |
| derived_statistics | 必需 | calculation_revision + metric_statistics；可选分组和配对统计；主比较各条件同样可见 |
| metadata | 必需 | 其中 age_band、timezone、device、quality_policy 为共同输入；synthetic、data_origin 等 provenance 内部留档 |
| designer_notes | 必需 | intended_pattern、expected_difficulty、stratum、rationale、matched_group；仅开发，不给模型 / 标注员 |

### 1.1 原始 observations

每个 daily row 有 `date`、`daytime_wear_minutes`、`metrics`、`missing_reasons`，可选 `nighttime_coverage_minutes`、`activity_intervals` 与 `low_movement_intervals`。date 是该日当地日期。睡眠按醒来日期归属；activity / steps 按自然日归属。前一日活动与当夜睡眠的关联需按真实区间对齐，不能把醒来日的白天活动误当作前夜暴露。

`metrics` 的字段固定命名：

| Metric | Unit / 类型 | 限制 |
| --- | --- | --- |
| sleep_duration_minutes | min，number / null | 设备估計的总睡眠时长，不是睡眠起止之差；不自动代表质量 |
| sleep_start_at / sleep_end_at | ISO 8601 timestamp with offset / null | 睡眠实际起止估计；跨午夜保留完整日期，不写模糊 01:00 |
| steps | count，integer / null | 0 是有效测量的零，null 是无可用测量 |
| activity_duration_minutes | min，number / null | 统一为设备估计 moving / active 时间；不是已知中等强度或 AHA zone minutes |
| low_movement_minutes | min，number / null | 设备估计低移动，不能自动称为确认坐姿 / sedentary physiology |
| resting_heart_rate_bpm | bpm，number / null | 同一设备的日估计，不能与瞬时心率混用 |
| hrv_rmssd_ms | ms，number / null | 同一 RMSSD 估计和采集窗口，不能混用 SDNN 或不同设备算法 |

主数据的所有 case 用相同 metric 键集合，未知值写 null。示例只展示两种 metric 来缩短完整例子，不是最终 24 case 的字段覆盖规范。设备能力不支持的 metric 写 null 并解释 `not_supported`，不能伪造观测。`daytime_wear_minutes` 指日间观测区间的有效佩戴分钟，与睡眠覆盖分开；原始导出无该覆盖量时写 null，不填 1440；例子里的 900 等为合成覆盖数据。

missing_reasons 中每个 null metric 必须有一种原因：`not_worn`、`insufficient_coverage`、`device_error`、`not_supported`、`unknown`。非 null metric 不得对应 missing reason。不存在的 metric 不可用 0 填充。不插值用于主标注或主比较；如开展插值 sensitivity analysis，独立记录版本并让所有条件相同。

区间对象是 start_at / end_at，时间戳带 UTC offset；按起点排序，start < end，同类区间不重叠；跨自然日区间在午夜拆分，sleep 区间除外。活动区间的 `intensity` 只能是经记录的 `light/moderate/vigorous/unknown`；主 pilot 默认 unknown，不从 steps 或心率猜强度。区间和 daily 总量应与同一统计定义一致。低移动与活动不要求完整覆盖一天，未观测时间不能当作坐着。

质量规则统一且在生成前固定：例如 steps / 日活动主分析要求日间有效佩戴至少 720 min；夜间睡眠 / HRV 用另外的睡眠覆盖规则。数值只是本 benchmark 的 quality policy，不是厂商统一标准。不同 metric 的有效性独立判断。未提供夜间覆盖时不得据日间佩戴时长宣布 HRV 有效。daytime_wear_minutes 与当天相交的夜间覆盖不能合计超过 1440；按醒来日归属的整夜覆盖可能跨两天，校验时要拆分时间。

### 1.2 derived_statistics 必须可重算

calculation_revision 当前为 `stats-v1`，每个数值指标有 baseline / window 统计及 comparison。

| 统计字段 | 固定计算定义 |
| --- | --- |
| valid_count / missing_count | 非 null / null 个数，二者之和等于该 period 日历天数 |
| mean / median / min / max | 仅使用有效观测；无有效值则 null |
| variance | population variance，分母 n；n=1 为 0，n=0 为 null，单位为原单位平方 |
| slope_per_day | 对实际日历天偏移做 OLS，不能删缺测后重新编号；有效点少于 2 为 null |
| adjacent_mean_abs_delta | 只比较相邻日历天且两天均有效的绝对差；无有效相邻对为 null；不跨缺测连接 |
| mean_difference | window_mean - baseline_mean；任一缺失为 null |
| relative_mean_difference | 上项 / baseline_mean，fraction 而非 percentage；baseline_mean=0 为 null |

统计落盘保留至少 6 位小数精度，展示再舍入；验证时用绝对 + 相对误差，不凭打印小数判断。所有值必须是有限 JSON number，不能输出 NaN / Infinity。除了 counts，其他统计允许 null。

睡眠钟点统计使用 `sleep_start_minutes_from_local_noon` / `sleep_end_minutes_from_local_noon`：对每次睡眠，以其醒来日的前一日 12:00 当作 anchor，计算本地实际起止的分钟偏移。例如 23:00 是 660，次日 01:00 是 780。这保证跨午夜不会做出 23:50 和 00:10 的伪平均。转换有固定适用时段，主 pilot 不跨 DST / 时区；如果 anchor 不适合某段白天睡眠，先记录而不是静默绕回。

可选 grouped_statistics 给 weekday/weekend 的相同统计字段，周一至周五 / 周六周日由 date 决定，不等于该人的工作 / 休息日。可选 paired_statistics 仅给 metrics、lag_days、paired_count、pearson_r；`lag_days=1` 表示 x 在 t 日与 y 在 t+1 日配对，null 不配对，n<3 或零方差时 r=null。少量点的 r 不是因果证据，且所有方法获得同样统计。

频率在 `frequency_statistics` 记录 metric、period、operator、threshold、matching_count、valid_count、longest_run_days：必须来自事先统一列出的纯数值 predicates，不针对某个 case 单独设“恰好命中”的阈值；null 不算命中且打断连段。可使用 sleep_duration_minutes < 420 作为数值计数，但字段不得命名 sleep_debt_days，且该计数不自动定义 relevance。窗口为空等状态与无命中分开。主 pilot 可以不提供频率字段，由表示自行从同样原始输入选择信息。

禁止包括：diagnosis、stress、sleep_debt、circadian_disruption、recommended_action、knowledge_ids、expected_relevance 等预解释字段。不能用全语料词汇抽取结果作为“确定性统计”。

### 1.3 模型视图必须用白名单

Representation 输入仅包括：window_days、baseline_days、periods、observations、derived_statistics，以及 metadata 中 age_band、timezone、device、quality_policy。不包括 id、case_type、schema_version、synthetic、data_origin、designer_notes、matched_group。后台保存关联键，不让 C001 等成为提示线索。不能仅删除 designer_notes 而仍把整个对象塞给模型。

标注员看原始 observations、必要的已复核数学统计、影响适用性的同一 metadata、knowledge title / content / 来源适用条件；不看 case 规划、stratum、designer_notes、任何生成文本或检索结果。

## 2. 一个完整示例

[examples/wearable_case.example.json](../examples/wearable_case.example.json) 是完整可解析对象，包含 C008 的全部 42 天日值，不以自然语言或均值替代 baseline。它是明确标为 synthetic 的 schema example，不是正式 gold case。

示例原始字段节选如下；完整 baseline / window 和全部统计请读 JSON 文件：

```json
{
  "date": "2026-04-08",
  "daytime_wear_minutes": 360,
  "nighttime_coverage_minutes": 480,
  "metrics": {"sleep_duration_minutes": 450, "steps": null},
  "missing_reasons": {"steps": "insufficient_coverage"}
}
```

完整统计是：baseline steps mean 9500（28/28），window mean 6523.076923（13/14），difference -2976.923077，relative difference -0.313360324；睡眠两段 mean 均 450 min。没有把 null 日算成零，也没有“活动不足”“压力”等标签。

## 3. Knowledge item schema

正式格式由 [knowledge_item.schema.json](../schemas/knowledge_item.schema.json) 定义，核心包括：schema_version、id、status、domain、title、content、source、source_url、source_locator、source_accessed_on、language、keywords、applicability、provenance。

id 为 K001-K096。status 为 draft 或 verified。draft 可以 content=""、source=null 等，不能进入实验；verified 必须有经人工检查的正文、真实出处与定位信息。source_accessed_on 是实际核验日期，不能猜网页发布时间。未知发布时间允许 provenance.source_published_on=null。仅访问网页并不使条目自动 verified。

applicability 是人工由正文和来源提取的审查信息：population、observable_conditions、required_context、non_applicable_conditions。不能从某个 case 的期望答案反推条件，也不能给来源没有的数值阈值。它们供独立标注和审查，主检索只索引 `title + content`，不额外索引 domain、keywords、applicability、case ID 或 relevance。标题用自然语言、保留必要的条件，不直接用 schema 字段名当标题，也不故意隐去普通健康关键词。

provenance 至少记录 content_revision、editorial_status、source_published_on、license_note；完成内容应是简洁的自主概述，不复制整段版权文本。设备测量解释条目与健康行为条目分开分类和报告。

如下只说明 draft 状态的写法，不是真实医学知识，也不写入 knowledge_items.jsonl：

```json
{
  "schema_version": "1.0",
  "id": "K001",
  "status": "draft",
  "domain": "sleep_duration",
  "title": "为休息留出足够的时间",
  "content": "",
  "source": null,
  "source_url": null,
  "source_locator": null,
  "source_accessed_on": null,
  "language": "zh-CN",
  "keywords": [],
  "applicability": {
    "population": [], "observable_conditions": [],
    "required_context": [], "non_applicable_conditions": []
  },
  "provenance": {
    "content_revision": "draft-v1",
    "editorial_status": "pending_source_review",
    "source_published_on": null,
    "license_note": "尚未整理正文"
  }
}
```

## 4. Relevance records

最终 `relevance_labels.csv` 仅三个字段 `case_id,knowledge_id,relevance`，relevance 为 0/1/2。每 pair 唯一、全矩阵覆盖、引用真实 ID。与之分开的 annotation_form 保存 annotator_id、独立评分、status、raw_data_evidence、item_condition_evidence 和理由；标注不足时 status=needs_review，relevance 留空，不能悄悄转成 0。未裁决的 pair 不进入冻结版本。详见 [annotation_guideline.md](annotation_guideline.md)。
