# C1 benchmark 设计

## 1. Design rationale

研究问题限定为 information selection 与 candidate retrieval：同一份原始纵向数据，经过不同目的的压缩后，检索所需的信息是否发生变化。结果可以支持 C1，也可以显示普通摘要已经足够，或额外保留的信息增加噪声。候选检索中的排序只用于计算检索质量，不涉及最终健康建议排序。

采用 24 个 case、96 个 atomic knowledge items。四个主要 case 类型各 6 个，每类型内部各有 2 个 A、2 个 B、2 个 C，总计 A/B/C 各 8 个。A = easy；B = representation-sensitive 的待检验设计；C = negative / distractor。类型描述主要构造轴，不要求其他变量完全静止。

这些是设计 strata，不是 gold 结论。B 不意味着 summary 必败；C 不意味着整条 relevance 向量全零。难度与 summary 是否足够都是先验设计判断，随后应由实际压缩输出和盲标检验。Synthetic balanced sample 用于识别失败机制，不能估计真实人群中的效应或频率。

统一使用 14 天目标 window 和紧邻的 28 天 baseline，覆盖整数周，避免工作日数量差异成为意外混杂。28 天是小规模构造的取舍，不声称等价于稳定的长期健康基线；未来如换为 90 天，所有方法接收同一份原始 baseline，并记录版本。保留日值、时间戳、缺测和需要时的活动 / 低移动区间。所有 case 都保留同一组少量背景变量，不能让“某字段出现”直接编码病例类型。

样本限定为 18-60 岁成人、非轮班、同一时区、无已知诊断任务。未观测的症状、饮食、药物、职业、压力、感染、运动强度不补写成事实。RHR/HRV 是设备估计值，不能据此生成疾病或压力 gold。低移动时间也不是经过姿态传感器确认的坐姿时间。

## 2. 24 个 case 的完整规划表

表中 `~` 表示目标中心及合理小幅波动；数字不是已生成的数据或医学判断。小时是文档展示单位，落盘睡眠 / 活动时长统一为分钟。每条最终记录包含睡眠时长、睡眠起止时间、steps、活动时长、低移动估计、RHR、同一定义的 HRV 及覆盖质量；“variables”列列出主要检验变量。静态背景变量具有适度自然波动，不复制同一条固定背景序列。

| ID | Case type / stratum | Wearable variables | Longitudinal pattern | Intended difficulty | 想检验什么 | Generic summary 理论上是否足够 |
| --- | --- | --- | --- | --- | --- | --- |
| C001 | 单变量显著变化 / A | 睡眠时长 | baseline 7.5-8 h；window 14 晚均为 5.5-6 h，覆盖完整，时点稳定 | easy | 明显且持续的单一事实，无复杂条件也能召回 | 是；准确说明连续睡得较少即可 |
| C002 | 单变量显著变化 / A | steps | baseline ~8000；window 每天 2000-3000，日间佩戴完整 | easy | 显著低活动是否被普通摘要捕获 | 是；不需要复杂时序描述 |
| C003 | 单变量显著变化 / B | 睡眠时长 | window 前 7 晚 ~8 h，后 7 晚 ~6 h；baseline ~8 h；与 C005 的 window 值多重集合相同 | sensitive | 相同均值 / 分布下，近期恶化方向是否丢失 | 仅均值不够；保留后半段下降的摘要可以足够 |
| C004 | 单变量显著变化 / B | HRV RMSSD | baseline ~45 ms；window 第 5-8 晚为 22-28 ms，其余回到个人常见范围 | sensitive | 连续局部波动、频率和恢复是否改变监测类候选，而非压力诊断 | 条件性；写清四晚连段和随后回归即可 |
| C005 | 单变量显著变化 / C | 睡眠时长 | window 前 7 晚 ~6 h，后 7 晚 ~8 h；baseline ~8 h；与 C003 同均值及直方图 | distractor | 已回归的短暂变化是否被当成仍持续的问题；历史主题可仍为 1 | 条件性；恢复过程应能用一句话说明 |
| C006 | 单变量显著变化 / C | HRV RMSSD | 13 晚在个人常见范围，仅 1 晚较低；数据覆盖完整，其他信号稳定 | distractor | 单点显著值是否触发不受支持的压力 / 疾病或持续改变知识 | 是；应说明孤立值和其余稳定，不能推断原因 |
| C007 | Personal baseline / A | 睡眠时长 | baseline ~5.5 h；window 14 晚回升至 ~7.5 h，时点稳定 | easy | 明显改善方向的控制，不能把所有变化都理解为恶化 | 是；“近期睡眠时间回升并较规律”的普通摘要可以足够 |
| C008 | Personal baseline / B | steps；睡眠作背景 | baseline ~9500；window ~6500；睡眠不变，有 1 天 steps 因低覆盖为 null | sensitive | 不显眼的当前量是否因个人降幅成为监测候选；缺测不算零 | 条件性；包含“比自己此前少约三成”的摘要也可以足够 |
| C009 | Personal baseline / B | RHR | baseline ~52 bpm；window ~62 bpm 持续 14 天，HRV 等背景稳定 | sensitive | 相同当前值下个人变化是否帮助召回记录 / 复核类知识 | 条件性；需要个人此前水平，不需要疾病词 |
| C010 | Personal baseline / A | steps | baseline ~2800；window 持续回升至 ~8000，覆盖完整 | easy | baseline 路径内的明显回升，检验维持 / 记录进展主题而非低活动误检 | 是；“日常活动明显回升”的摘要无需精细统计也可以足够 |
| C011 | Personal baseline / C | RHR | baseline 和 window 均 ~62 bpm；当前序列与 C009 一样，只有 baseline 不同 | distractor | 常见数值是否被误读成“相对本人升高” | 是；没有变化，不强制召回变化触发条目 |
| C012 | Personal baseline / C | HRV RMSSD | baseline 变异较宽、中心 ~40 ms；window 在此前常见范围内分散波动，无持续同向变化 | distractor | 相对个人波动范围和不确定性，防止套用统一 HRV 正常值 | 条件性；表述常见范围内波动即可；不能用跨人阈值 |
| C013 | Temporal pattern / A | 入睡和醒来时间；睡眠时长 | window 中反复交替相差 2-3 h 的睡眠时点，时长仍 ~8 h；baseline 规律 | easy | “时间不规律但时长足够”这个普通 insight 是否足够 | 是；允许摘要直接保留显著时点波动 |
| C014 | Temporal pattern / A | 活动时长；steps | 14 天几乎每天活动估计仅 0-10 min，steps 同样较低，覆盖完整 | easy | 日复一日低活动不必复杂 temporal encoding | 是；不能把未知强度时长换算为中等强度分钟 |
| C015 | Temporal pattern / B | 睡眠时长；入睡 / 醒来时间 | 两周均为工作日 ~6.5 h、周末 ~9.5 h；周末起止时点后移，baseline 无此差异 | sensitive | 整窗均值掩盖工作日 / 周末差异；不是自动诊断节律障碍 | 条件性；写出两个分组的摘要可以足够 |
| C016 | Temporal pattern / B | 低移动区间；总活动 | 每天累计低移动 ~480 min，存在 120-180 min 连段；活动总量与 C018 匹配 | sensitive | 相同日总量下持续段与分散段的检索区别 | 仅总量不够；“有长时间连续低移动”可足够 |
| C017 | Temporal pattern / C | 入睡 / 醒来时间；睡眠时长 | baseline 与 window 均为规律 01:00-09:00、~8 h，无时差 / 轮班元数据 | distractor | 晚钟点本身不证明不规律、睡眠不足或节律疾病 | 是；不能仅凭“晚睡”关键词制造问题 |
| C018 | Temporal pattern / C | 低移动区间；总活动 | 每天低移动总量同 C016，但每段 10-20 min 且由移动打断；活动总量匹配 | distractor | 日总量相同不证明有长连续段；一般少坐知识可仍为 1 | 条件性；需要段结构，不能从日总量猜出 |
| C019 | 多变量组合 / A | 睡眠时长 + steps | 全窗分别为 ~5.5 h 和 ~2500，两者都清楚，其他指标无显著变化 | easy | 两个独立明显事实的并集，普通摘要已经足够 | 是；无需推断两者因果关系 |
| C020 | 多变量组合 / A | 活动时长 + 低移动估计 | 每天活动 ~10 min、低移动 ~600 min，有完整覆盖 | easy | 多变量并不自动等于复杂 reasoning | 是；逐项描述即可 |
| C021 | 多变量组合 / B | 活动时间段 + 当夜睡眠 | 6 个晚间长活动日之后睡眠较短；非该活动日较长；与 C023 匹配活动和睡眠边际分布 | sensitive | 跨日对齐信息能否支持“记录并复核时间安排”的候选 | 条件性；写清对齐关系可足够；不允许“运动造成失眠” |
| C022 | 多变量组合 / B | RHR + HRV | 同一 4 晚 / 日的 RHR 上移、HRV 下移，其余回到 baseline；与 C024 各变量边际分布相同 | sensitive | 同期性是否增加受支持的监测知识价值，或者只是多余信息 | 条件性；保留同一时段的事实即可；不诊断压力或恢复不足 |
| C023 | 多变量组合 / C | 活动时间段 + 当夜睡眠 | 与 C021 相同边际值，通过固定置换使短睡眠均匀落在活动及非活动日 | distractor | 仅共存是否被错误当作关联；额外信息可能诱发过度召回 | 条件性；需要说明缺少稳定时间对应，不能虚构独立性证明 |
| C024 | 多变量组合 / C | RHR + HRV | 两个方向各自的 4 次变化分布在不重叠日期，边际值同 C022 | distractor | 聚合后“同时变化”的假象；分开波动仍可支持各自监测候选 | 条件性；明确不同时发生即可 |

冻结前的构造约束：C003/C005、C009/C011、C016/C018、C021/C023、C022/C024 为匹配组。同组使用相同设备定义、背景数据、缺测规则和当前值 / 边际匹配条件，只有预注册的目标轴不同；每组一起重采样。C021/C023 应在同一 weekday 分组内选择置换，避免把曜日分布变成额外线索。保留 case 级结果，但 5 对匹配 case 的统计独立单位是组，另外 14 个 case 是单独单位，共 19 个单位。

为检验“多留信息反而有噪声”，所有 case 均有少量非判别背景信号；C006/C012/C023/C024 特别观察噪声召回。禁止只给 B 或 C 添加许多无关字段。主要 comparison 下，各方法读取相同原始数据及相同 deterministic statistics。

如果 source-grounded knowledge 并没有区分同期性、变化方向或 baseline 的适用条件，不能把 matched cases 硬标成不同 gold。该匹配组只能检验信息保留；对 retrieval loss 没有识别力。必须在冻结前记录这一事实，补充可核验知识或将该检验降为探索性；不能根据某方法得分事后补知识。

## 3. 公平比较与读数

### 3.1 控制条件

建议登记三个条件的实验位置，不在本轮实现其方法：generic summary、面向用户的 insight、retrieval-oriented representation。若没有经过核验的 PHIA 实现或可复现流程，不把自写摘要称为 PHIA；只能称作本研究的 insight baseline。

各条件接收同样的 `model_input` 白名单，采用同一生成模型版本、语言、最大输出 token 预算、调用次数和随机性设置。建议预算为每 case 256 output tokens；预先固定，不为了容纳 Evidence 的字段给它额外窗口。主比较均可访问相同的统计；另外比较仅原始记录的输入设置时，所有条件同步切换。记录实际输出长度；统一处理截断、空输出和失败，空输出的候选列表为空而不是重试到成功。

Summary / insight prompt 应认真服务于用户目的，并允许保留显著的数量、持续性、baseline 和时序事实；不能要求它删掉这些信息。禁止任何方法看 knowledge corpus、标签、规划表、designer_notes 或 case_type 来生成 representation，否则混入 corpus-aware query generation。语义表示格式和字段选择属于后续方法工作，本轮不规定一个天然含所有答案的 Evidence 模板。

主条件直接把生成文本作为单一检索输入，采用同一个 frozen retriever、同一个 corpus title + content 视图和同一个候选数。若未来需要 query rewriting，则所有条件共用相同重写步骤和预算，另外报告不重写版本。仅检索中使用的顺序不等于 recommendation ranking。

预注册两个实际检索实现作为诊断，例如 BM25 lexical recall 和固定版本的 dense embedding recall，分别跑分，不默认存在 hybrid。版本、分词、索引字段、相似度、tie-break、查询截断和 embedding 限制须在执行前固定。Retriever 差异检验交互效应，不能只报告最好的一条路径。固定 score tie 时用 knowledge_id 升序，不混入 gold。另以原始数值事实清单作为透明的检索参照，标为参照而非最终方法或性能上界。

### 3.2 终点及分析单位

Primary：`nDCG@10` 的 case 级配对差值，gain 为 `2^relevance - 1`，折扣为 `log2(rank + 1)`。有至少一个正例的 case 纳入 nDCG；全零 case 的 IDCG 为 0，记作 N/A，不定义为 1 或 0。报告被排除数量，并单独评估全零 case。若没有正例 case 或根本没有等级 2，必须报告终点退化，不能虚构 graded retrieval 证据。

Secondary：`Recall@10` 对 `relevance >= 1` 的召回，以及单独针对 `relevance == 2` 的 strong recall；分母为 0 时 N/A。`irrelevant_fraction@10 = top10 中 gold=0 的数目 / 实际返回数`，空列表另报 empty rate，不以空列表得到“完美 precision”。固定返回 top10 是 discrimination 读数，不自动代表系统向用户显示 10 条；若实验涉及 abstention / score threshold，阈值在独立开发数据上固定，并报告全零 case 的返回数和 false activation，不能在这 24 条上调整。

在有充分 golden 条件支撑的匹配组中，查看正确条件对应条目的召回与混淆；不根据 “B” 身份定义正确条目。A/B/C 与四类结果都给出，但为低样本探索性分层，不逐格做许多显著性检验。

每个生成条件建议 3 个固定种子 / 重复，先在 case 内聚合，然后做配对差值；重复生成不是新 case，2304 个标签也不是 2304 个独立受试者。以 19 个构造组为 cluster，给出 effect size、case 原始点及 cluster bootstrap 95% interval（例如 10000 次，固定种子）。小样本区间仅反映此 synthetic pilot，不能泛化成人群置信区间；不将多次跑分扩大成样本量。建议 primary comparison 固定为 BM25 下 retrieval-oriented representation 对 strong generic summary 的 nDCG@10 差值；insight 对比、dense 检索、分层与 ablation 均标 exploratory，不选出最大增益作为 primary。具体实现版本及 prompt 在独立开发材料上固定。

同时盲审压缩的信息保留：从原始数据建立独立事实表，检查单位、时间范围、baseline、缺测、变化方向、日期对齐是否被正确保留 / 错写。不能用规划中的 expected retrieval topics 当事实表。普通摘要即使不用结构字段，表达正确也算保留。单独报告输出中无来源的健康语义断言。

预注册 smallest effect of interest，例如 nDCG 的绝对增量 0.05，仅作为 pilot 的实际意义参考，并登记可接受的负例退化范围。结果可能是：增益有可见迹象；多数摘要已足够；Evidence 保留更多但检索未利用；额外信息降低 discrimination；或区间过宽而结论不确定。单次不显著不证明两目标等价，单次显著不证明最终方法优越。下一阶段的样本量依据方差和失败类型规划，不承诺 CCF-A 结论。

## 4. 对 benchmark 的 10 项攻击

| 攻击问题 | 设计处理与冻结前必须检查的证据 |
| --- | --- |
| derived statistics 写了答案吗？ | 只允许算术量；无 sleep debt / stress / disruption；重算统计并审查字段名；所有方法同样可见 |
| domain / case 标签泄漏吗？ | case_type、stratum、designer_notes、IDs 和 knowledge.domain / keywords 不进入生成输入或主索引；人工与检索接口使用不同视图 |
| 语料靠关键词就够吗？ | 每个主要主题安排适用条件不同的近邻；跑 lexical reference；高 lexical 分数本身不算失败，应据实报告任务较易 |
| 全部偏向纵向 reasoning 吗？ | 8 个 A、8 个 B、8 个 C；A 含多变量但不需要关系；不把 B 强标成 summary 必败 |
| summary 应成功的案例存在吗？ | C001/C002/C007/C010/C013/C014/C019/C020；允许摘要包含显著时序和 baseline，检查其实际内容 |
| similar-but-irrelevant distractor 存在吗？ | 由最终正文和原始记录盲标确认，每 case 审查至少两个相近但条件不满足的 corpus 邻居；不能只靠规划承诺 |
| baseline information 有识别力吗？ | C009/C011 当前数据匹配；C008 与 easy baseline 控制共同观察；必须有可核验的变化适用知识 |
| temporal compression loss 能测吗？ | C003/C005 保持 window 多重集合；C016/C018 保持总量；分别审查 representation 保留与 retrieval 命中 |
| multi-variable 信息必要吗？ | C019/C020 是独立并集控制；C021/C023、C022/C024 保持边际，仅在来源支持关系条件时比较 retrieval 差异 |
| 更多信息反而有噪声能测吗？ | 背景变量统一；C006/C012/C023/C024 观察误检；等预算输出，报告长度、无根据语义和 irrelevant_fraction |

## 5. 严格 reviewer 的五个 validity threats

| Threat | 为什么可能毁掉结论 | 必须处理的条件 / 无法解决的后果 |
| --- | --- | --- |
| 1. Case / corpus / gold 共同迎合假设 | 同一作者先写“应该匹配”再造正文和标签，尤其容易把复杂模式变成答案线索 | 独立盲标、冻结记录、条件来源复核；gold 依赖 Evidence / 规划表则不能用于检验 C1 |
| 2. 知识适用性不支持可穿戴关系 | HRV/RHR 变化不能诊断压力；每日总量不能代表强度或坐姿；同期关系也不证明因果 | 知识内容与可观察条件逐条对照；无法支撑组间 relevance 差异时不能声称 longitudinal 信息提升健康知识检索 |
| 3. 比较资源或 baseline 不公平 | Evidence 的额外 token、特权统计、较强模型、多个查询、故意弱 summary 都可能制造优势 | 同输入 / 同资源 / 强 summary 控制、实际长度与失败审计；条件不公平则不能把增益归因于信息选择目标 |
| 4. Retriever 与 corpus 的人为构造效应 | 近重复、刻意关键词、设备知识过多、不同 embedding 对 JSON / prose 的偏好都会改变结果 | 两条 frozen 检索诊断、独立信息保留审查、健康知识与设备知识分项报告；若只有某个编码 / retriever 有效，结论必须限定在该实现 |
| 5. 合成数据小样本与相关性 | 24 条、五对匹配、四类均衡，不代表真实分布；整齐模式可能比真实噪声容易得多 | 不把 labels / repeats 当独立样本；按构造组统计，展示全部点；无外部真实数据复验则只作可行性和失败机制结论 |

没有独立且有条件依据的 gold、没有公平的 representation 比较、或关系条件根本不可观察，这三类问题任一未解决，pilot 的分数都不足以回答 C1。若全部正例都是广泛健康常识、matched pair gold 不变、或全部靠字段 / 标题关键词即满分，pilot 也没有足够区分度；应在跑分前修订并重冻，而不是事后解释 Evidence 为什么赢。
