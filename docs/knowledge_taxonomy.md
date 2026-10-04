# 96 个 knowledge items 的 taxonomy

这是 corpus 建设配额，不是已经存在的 96 条医学内容。配额精确合计 96；每个 domain 的实际条目仍需来源、正文和审查。主 retrieval 只索引自然语言 title + content；domain / keywords 是建设与审计信息，不给生成条件，也不进入主索引。

## 1. 分配与容易混淆的主题

| Domain | ID 范围 | 数量 | 应覆盖的 atomic themes | 条件相近但应区分的邻居 |
| --- | --- | --- | --- | --- |
| sleep_duration | K001-K016 | 16 | 为休息留出时间；多晚时间不足；年龄适用范围；规律但偏短；时长与质量的区别 | 长期较少 vs 单晚较少；充足时长但不规律；未知质量 vs 已有主观症状 |
| sleep_timing | K017-K032 | 16 | 稳定作息；起床时点；工作日 / 周末差异；临时日程变化；晚间日常习惯 | 稳定的晚时点 vs 时点反复变化；时长不足 vs 时间不规律；轮班 / 时差专属条件未知时不适用 |
| temporary_variation | K033-K040 | 8 | 记录短期变化；回到常规作息；连续变化与孤立波动；睡眠日记中的时间范围 | 当前持续变化 vs 已结束的变化；记录与复核 vs 宣称“补睡能消除损失”；不得凭空添加恢复天数阈值 |
| daily_activity | K041-K056 | 16 | 日常增加活动；从较少活动逐步开始；总量与强度区别；分次活动；习惯维持 | steps 较少 vs 已知中等强度时间不足；单日降低 vs 持续降低；已有活动 vs 活动减少；具体强度知识可能不适用 |
| low_movement | K057-K068 | 12 | 减少少动时间；日间移动机会；低移动估计和实际坐姿差异；连续段与累计量 | 长连续段 vs 分散短段；有运动但其余时间少动；设备缺测 vs 真正少动；不能套用未经来源支持的“每 30 分钟”规则 |
| activity_sleep_context | K069-K076 | 8 | 活动安排与休息记录；晚间活动习惯；足够休息时间；睡眠日记记录运动时点 | 时间上相邻 vs 不相邻；日间活动与晚间活动；观察关联 vs 已证实因果；一般活动益处与个体时点问题 |
| personal_monitoring | K077-K088 | 12 | 同条件重复记录；个人趋势；RHR 和运动时心率区别；单信号与多信号的观测限制 | 相对自己变化 vs 跨人比较；单点 vs 持续；RHR vs sleeping HR；HRV RMSSD vs SDNN；有症状知识在症状未知时不适用 |
| measurement_quality | K089-K096 | 8 | 佩戴覆盖；null 与零；同设备比较；传感器 / 算法差异；估计值与诊断区别 | 真变化 vs 未佩戴；日间与夜间覆盖；不同设备切换 vs 同设备趋势；设备测量解释不是健康行为建议 |
| **合计** | **K001-K096** | **96** | | |

每条主要对应一个判断 / 教育主题，不是把长段落拆成多个近重复 item。可以有语义相近主题，但适用条件必须由来源支持。不要为每个 wearable feature 编写一条恰好同名的“答案”，也不要让标题与 schema 的 snake_case 字段一一对应。自然标题例如“为休息留出足够的时间”“把作息变化记录下来”，不是 `sleep_duration_minutes` 或 `baseline_difference`；仍允许正常的 sleep、activity 等词，不能故意为难 lexical baseline。

建议冻结前检查每个主要 topic cluster 至少有两个正文相近、条件不同的候选；是否构成某 case 的负例最终由独立标注决定。不要求每 case 具有固定数目的等级 2，不能人为调整标签分布。主 corpus 中 healthy lifestyle item 与 measurement item 分开报告，以免大量设备术语匹配掩盖健康知识任务。

不写进 corpus 的内容：可穿戴数据推断糖尿病 / 抑郁 / 感染；诊断 sleep apnea；由 HRV 自动判断压力；由相关性宣布运动造成失眠；由步数换算未记录的活动强度；具体用药或医学治疗。即使这些词在权威页面上出现，也不代表本任务有足够证据使其相关。

## 2. 已核验的来源入口

以下页面已于 2026-10-03 实际打开，仅核验适合作为后续采集入口；没有创建或逐条核验 96 条正文。每个完成 item 仍需对应 source_locator、实际核验日和正文适用条件。NHS / MedlinePlus 可以后续补充，不给未打开页面虚构引用。

| 来源 | 已检查的内容范围 | 当前不能由该入口直接声称的内容 |
| --- | --- | --- |
| [CDC: About Sleep](https://www.cdc.gov/sleep/about/index.html) | 年龄相关睡眠时长、一般睡眠习惯、睡眠日记项目 | 不能仅用估计时长诊断睡眠疾病或推断主观困倦 |
| [NHLBI / NIH: Healthy Sleep Habits](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits) | 保留休息时间、较一致的作息、周末与工作日安排、日间活动及睡前习惯 | 不能证明某人的晚间运动导致其睡眠变化，也不提供任意的补睡恢复公式 |
| [CDC: Adult Activity](https://www.cdc.gov/physical-activity-basics/guidelines/adults.html) | 成人活动建议、可以分次累积活动、move more / sit less | steps 与未知强度 active minutes 不能自动判断中等强度达标 |
| [AHA: All About Heart Rate](https://www.heart.org/en/health-topics/high-blood-pressure/the-facts-about-high-blood-pressure/all-about-heart-rate-pulse) | 心率、测量情境及影响因素；单一心率观测的限度 | 不能把“较个人以前高”改写为疾病或紧急状态，未知症状不得补入 |
| [Google Health / Fitbit: Track Your Heart Rate](https://support.google.com/googlehealth/answer/14237938?hl=en) | 设备佩戴与信号准确性、设备 / 算法差异、RHR 与 sleeping HR 区别 | 厂商文档不是 RHR/HRV 联合诊断的临床验证 |

以上是内容范围的概述，不是原文引用。尚未核验 HRV 的具体算法来源、连续低移动的细粒度健康条件或每种恢复主题；这些 quota 能否充分支撑是冻结前的开放问题，不能用上述五个 URL 为所有拟定主题统一背书。

## 3. 建设、独立审查与冻结

1. 先整理与 case 规划分开的来源主题清单和 atomic 正文，保留真实定位和未知信息。
2. 用一个独立内容审查者核验正文、population、observable_conditions、required_context、non_applicable_conditions；不能只写“来自 CDC”。
3. 对语义相近条目检验是否只是改写重复；合并近重复，保留有来源依据的条件差异。
4. 把 corpus 与原始 case 交给不知道方法输出的标注员。条件过宽导致所有 case 都匹配、或者条件无法从 D_t 确认时，在冻结前修订文本或 case 并重标。
5. 达不到 96 条独立受支持知识时，公开调整配额和 benchmark 版本；不能编来源、编适用阈值、或为了 Evidence 补写专用答案。
