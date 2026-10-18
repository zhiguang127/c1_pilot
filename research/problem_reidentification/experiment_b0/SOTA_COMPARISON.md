# B0：外部强基线与解释约束比较

状态：**COMPLETE_EXPLORATORY_EXECUTION**。这是没有独立优先级 Gold 的探索性执行，不是正式决策准确率评估。

## 数据、实现和原生边界

主比较固定全部 16 名真实参与者各最早窗口（block=0），每例原五候选，共 80 个不同案例—知识对。主比较每个方法计划 16 条窗口级记录，十个方法臂合计 160 条；四人候选顺序反转另 40 条，合计计划 200 条方法记录。重复方法和干预不是新的独立参与者。没有根据 S4 或其他模型错误挑选窗口，也不称这些已参与旧研究的参与者为全新盲测人群。

八个官方仓库、精确 SHA、许可、输入／训练要求、权重、可复用部分与阻碍见 [SOTA_BASELINE_AUDIT.md](SOTA_BASELINE_AUDIT.md)。RankingSHAP 的作者合成评分器及 TRACE 的官方 MovieLens-100K/SASRec 算法实际执行成功，但它们不进入健康推荐优先级准确率比较。RE2、ReRec、PEX-DPO 没有训练后模型的实际运行结果；B2 只能称 RE2-style Prompting。

本次 S3a=CRITIC-adapted+Grounding，S3b=S3a+Claim Validity，S4=S3b+Candidate-Relative；由用户授权新建，不冒充之前已存在的冻结定义。S4 本身是约束 Prompt 对照，不是已证实的新算法。

## 主比较的真实执行

下表“接受”仅表示统一结构通过。无效／失败都保留在 16 的计划分母中；后续行为配对只使用两侧结构均可接受的窗口，并显式报告配对分母，不能把这种筛选后的子集解释为性能优势。

| 方法 | 接受 / 已完成 / 计划 | 结构失败 / 执行失败 | 排序变化 / 可配对 B1 | 解释变化 | 适用性变化条数 | 工具交互 |
|---|---:|---:|---:|---:|---:|---:|
| B1 Direct Ranking + 独立事后解释 | 15 / 16 / 16 | 0 / 1 | 0 / 15 | 0 | 0 | 0 |
| B2 RE2-style Reason-then-Recommend Prompting | 12 / 16 / 16 | 2 / 2 | 11 / 11 | 11 | 4 | 0 |
| B3 Self-Refine-adapted | 15 / 16 / 16 | 0 / 1 | 5 / 15 | 14 | 7 | 0 |
| B4 CRITIC-adapted | 11 / 16 / 16 | 2 / 3 | 3 / 11 | 7 | 4 | 15 |
| B5 RARR-adapted Explanation-only Repair | 15 / 16 / 16 | 0 / 1 | 0 / 15 | 3 | 0 | 15 |
| S3a Grounding | 14 / 16 / 16 | 0 / 2 | 5 / 14 | 10 | 7 | 15 |
| S3b + Claim Validity | 11 / 16 / 16 | 2 / 3 | 7 / 11 | 8 | 4 | 15 |
| S4 + Candidate-Relative | 9 / 16 / 16 | 3 / 4 | 5 / 9 | 8 | 6 | 15 |
| Budget-Matched Self-Refine | 14 / 16 / 16 | 1 / 1 | 6 / 14 | 13 | 0 | 0 |
| Budget-Matched CRITIC | 13 / 16 / 16 | 2 / 1 | 3 / 13 | 13 | 6 | 15 |

RARR 的排序和适用性变化为零是接口锁定的结果，不是从数据发现它永远不能修改排序。原算法不含此健康排序目标；本轮没有额外 reranking adapter。执行成功的模型反馈、修正、query、tool result 和失败响应均保存在忽略的 `local/`，没有用测试夹具替代真实模型。

依赖共同初始化而未运行的修正记录共有 8 条，包含在表中执行失败列，但不能当成这些方法实际生成了错误答案；机器报告另列 `not_run_shared_initialization`。

## 字面证据检查

这里只检查 reference 存在、显式值及 null/零 RHR 的用途，不验证自由文本全部数值、医学语义、来源主张或优先级。空 evidence 单独记数；少引用不是正确性提高。

| 方法 | 有效引用 / 全部引用 | 无效引用 / 错值 / 无效生理用途 | 无引用 item / 接受的 item |
|---|---:|---:|---:|
| B1 Direct Ranking + 独立事后解释 | 61 / 163 | 102 / 0 / 0 | 1 / 75 |
| B2 RE2-style Reason-then-Recommend Prompting | 14 / 108 | 92 / 2 / 0 | 0 / 60 |
| B3 Self-Refine-adapted | 65 / 171 | 106 / 0 / 0 | 1 / 75 |
| B4 CRITIC-adapted | 28 / 108 | 80 / 0 / 0 | 1 / 55 |
| B5 RARR-adapted Explanation-only Repair | 61 / 163 | 102 / 0 / 0 | 1 / 75 |
| S3a Grounding | 63 / 160 | 97 / 0 / 0 | 1 / 70 |
| S3b + Claim Validity | 49 / 120 | 71 / 0 / 0 | 0 / 55 |
| S4 + Candidate-Relative | 38 / 106 | 68 / 0 / 0 | 0 / 45 |
| Budget-Matched Self-Refine | 59 / 152 | 93 / 0 / 0 | 1 / 70 |
| Budget-Matched CRITIC | 43 / 142 | 99 / 0 / 0 | 1 / 65 |

另作**事后格式诊断**：部分模型引用 `stats.phase.metrics.metric.stat`，恰好对应输入 JSON 的实际层级，但违反输出规范的四段写法。只在同一原记录能够解析时删除字面的 `.metrics` 层；不改 value、purpose、解释、适用性或排序，也不回写原预测。以下结果用于区分接口不符与真正错值，不是已运行的推荐修复实验，不能替代原严格结果或来源语义审查。

| 方法 | 仅格式映射引用数 | 映射后有效引用 / 全部引用 | 仍无效引用 / 错值 / 无效生理用途 |
|---|---:|---:|---:|
| B1 Direct Ranking + 独立事后解释 | 96 | 157 / 163 | 6 / 0 / 0 |
| B2 RE2-style Reason-then-Recommend Prompting | 90 | 104 / 108 | 2 / 2 / 0 |
| B3 Self-Refine-adapted | 99 | 164 / 171 | 7 / 0 / 0 |
| B4 CRITIC-adapted | 80 | 108 / 108 | 0 / 0 / 0 |
| B5 RARR-adapted Explanation-only Repair | 96 | 157 / 163 | 6 / 0 / 0 |
| S3a Grounding | 95 | 158 / 160 | 2 / 0 / 0 |
| S3b + Claim Validity | 68 | 117 / 120 | 3 / 0 / 0 |
| S4 + Candidate-Relative | 66 | 104 / 106 | 2 / 0 / 0 |
| Budget-Matched Self-Refine | 87 | 146 / 152 | 6 / 0 / 0 |
| Budget-Matched CRITIC | 93 | 136 / 142 | 6 / 0 / 0 |

## 资源、工具与预算对齐

所有修正臂使用字节完全相同的 B1 初始输出。CRITIC 与 ECR 的真实工具结果使用同一实现，均返回完整 42 行、质量标记、确定性统计、相同来源片段，无 Silver、Gold 或 Oracle。Self-Refine 在初始输入也拥有同一全部记录与统计。运行后已核查共同初始哈希 152 次，完整工具结果 114 次，当前均通过。

基础模型统一 `qwen-max`、temperature=0、同一 DashScope 端点；其供应商 alias 不是不可变权重。普通 Self-Refine 反馈/修正上限为 1024/2048；普通 CRITIC 两阶段各 2048。BM Self-Refine 两阶段各 3072，BM CRITIC 与三个 ECR 臂三阶段各 2048，最大输出总量均 6144、一次最终修正。RARR 检查/编辑最多 256+256+2048。所有臂同一 120000 UTF8 字节输入保护，不截断记录，真实 token 窗口由供应商校验。

这只是**分配的输出预算对齐**。实际输入 token、生成量、阶段分配与 Prompt 内容仍不同，不能把下面的比较当成完全相同 realized compute 的因果实验。相同工具权限已经核查，但仍不足以排除 Prompt/资源混杂。

| 方法 | 逻辑请求（含缓存） | 输入 token | 输出 token | 按公开价逻辑费用 ¥ |
|---|---:|---:|---:|---:|
| B1 Direct Ranking + 独立事后解释 | 31 | 251,311 | 14,687 | 0.7441 |
| B2 RE2-style Reason-then-Recommend Prompting | 30 | 246,166 | 19,856 | 0.7814 |
| B3 Self-Refine-adapted | 30 | 267,976 | 20,075 | 0.8359 |
| B4 CRITIC-adapted | 30 | 382,973 | 14,952 | 1.0627 |
| B5 RARR-adapted Explanation-only Repair | 35 | 179,782 | 5,426 | 0.4836 |
| S3a Grounding | 45 | 632,555 | 18,238 | 1.6932 |
| S3b + Claim Validity | 45 | 634,198 | 18,919 | 1.7037 |
| S4 + Candidate-Relative | 43 | 604,970 | 19,146 | 1.6357 |
| Budget-Matched Self-Refine | 30 | 267,478 | 19,069 | 0.8250 |
| Budget-Matched CRITIC | 45 | 630,649 | 16,651 | 1.6734 |

每臂逻辑费用只衡量它自己的新增阶段；共同 B1 初始化费用单列、不在每个修正臂重复收费。缓存重放不算新独立试验；工程失败费用包含在下方总账中。

| 配对 | 两侧有效窗口 | 不同排序 | 决策改善 |
|---|---:|---:|---|
| B4_critic__S4_relative | 6 | 4 | 无 Gold，不计算 |
| BM_critic__S4_relative | 8 | 5 | 无 Gold，不计算 |
| BM_self_refine__S4_relative | 9 | 7 | 无 Gold，不计算 |
| S3a_grounding__S3b_claim | 10 | 8 | 无 Gold，不计算 |
| S3b_claim__S4_relative | 6 | 6 | 无 Gold，不计算 |

## 候选顺序干预

预定四名参与者反转候选呈现顺序，记录与来源内容不改；重新运行所有臂。这里也重新生成共同 B1 初始化，工具包仍使用 canonical 候选顺序，所以只能称整个管线的行为稳定性检查，不能隔离最终修正步骤或证明临床反事实一致性。

| 方法 | 相同排序 / 两侧有效窗口 | 相同候选对关系 / 可比关系 |
|---|---:|---:|
| B1 Direct Ranking + 独立事后解释 | 0 / 4 | 23 / 40 |
| B2 RE2-style Reason-then-Recommend Prompting | 0 / 1 | 3 / 10 |
| B3 Self-Refine-adapted | 0 / 3 | 21 / 30 |
| B4 CRITIC-adapted | 0 / 1 | 6 / 10 |
| B5 RARR-adapted Explanation-only Repair | 0 / 4 | 23 / 40 |
| S3a Grounding | 0 / 3 | 17 / 30 |
| S3b + Claim Validity | 0 / 3 | 18 / 30 |
| S4 + Candidate-Relative | 0 / 2 | 10 / 20 |
| Budget-Matched Self-Refine | 0 / 1 | 5 / 10 |
| Budget-Matched CRITIC | 0 / 4 | 14 / 40 |

## Q1–Q7：当前能回答什么

| 问题 | 当前判断 |
|---|---|
| Q1 RE2-style 是否已有有效决策解释？ | 有真实的先 reasoning 再 recommendation 输出；没有运行 RE2 训练模型。结构接受和存在解释不证明解释有效或优先级正确，需盲审。 |
| Q2 普通 Self-Refine 能否修复同类错误？ | 普通反馈确实生成真实修正，行为和引用变化已记录；没有独立裁决的错误集，无法把改变称为修复，也不能认定普通反馈不够。 |
| Q3 同工具 CRITIC 能否达到 ECR？ | CRITIC-adapted 实际执行，拥有相同完整工具；有预算上限对齐配对。排序分歧和字面引用指标不能判定谁达到正确决策，因此没有 ECR 优势结论。 |
| Q4 RARR 解释修复与排序修复有何区别？ | RARR 的 gate 和 editor 真实运行，但程序锁定排序/适用性，能检查解释变化而不能贡献排序变化；其他修正臂可以改排序。零排序变化是设计结果，不是 RARR 效果差的证据。 |
| Q5 候选相对约束独有地修复了什么？ | 尚未建立任何其他强方法无法修复的错误类别。它可能抑制缺乏区分证据的严格优先对，但 tie 增多、文字变化或引用通过都不足以证明这种独有贡献。 |
| Q6 优势能归因于新机制吗？ | 本轮未建立决策优势。即便后续某项自动指标更好，仍有 Prompt 内容、实际 token、格式失败筛选、同家族模型与未确认来源范围等混杂。没有额外监督或 Oracle，但不能据此排除所有替代解释。 |
| Q7 既有工作对创新有什么限制？ | RE2/ReRec 覆盖推荐推理训练，Self-Refine/CRITIC 覆盖反馈和工具修正，RARR 覆盖证据编辑，RankingSHAP/TRACE 覆盖整体排序与相对反事实，PEX-DPO 覆盖预测解释一致性，RecPIE 覆盖解释反馈改善预测。不能再把这些宽泛概念主张为新贡献。 |

## 冻结、失败与交付

v1 的固定排序接口失败、v2 的 null-array JSON 接口失败、v3 的字节过度保守上下文保护失败都保留在 `local/protocol_history`、旧 runs 与原始 request/cache 中，三份旧 freeze 也提交。v4 只修正上下文保护、不截断数据；没有根据 S4 最终排序修改其他 Prompt。B2/其他臂后续的多 JSON、缺候选、截断等错误仍保留为失败，没有模型补标或按效果重试。故当前冻结发生在工程排错之后，不能声称未经任何开发暴露的确认性预注册实验。

初始来源 manifest 的部分历史 text SHA 与原 C1 冻结字节不同。B0 以已冻结 `data/input_freeze.json` 的实际文件哈希校验，并显式标出历史 manifest 是否匹配；未改来源、manifest 或任何 A 记录。旧 C1 77 个哈希、P1/A1 发布、Silver 发布、旧预测及原 Silver 标签文件均复核；见 [frozen_inputs_verified.json](results/frozen_inputs_verified.json)。

截至本快照共有 **481 个实际请求**、469 个已计量响应，输入 5,181,242、输出 224,843 token。按[已核验公开单价](https://help.aliyun.com/zh/model-studio/qwen-max)，不计缓存约 **¥14.5935**，按服务端缓存量约 **¥14.1486**。另有 12 个未获完整计量的请求，保留约 ¥0.9075 的保守预算占用；不能将它们写为零费用。B0 上限 ¥20，与旧 Silver 预算分开，实际账单未知。

机器聚合为 [comparison.json](results/comparison.json)，全部私人执行文件有内容哈希清单。审查规则见 [REVIEW_PROTOCOL.md](REVIEW_PROTOCOL.md)。最终仍需独立人工来源/解释检查、可判定优先级、更多参与者与窗口、固定初始状态的独立干预，以及真正 RE2/ReRec/PEX-DPO 训练对照。

**目前没有证据证明某种解释约束在强已有方法之外具有可靠的独立推荐决策贡献；允许最终结论是普通推理、反馈或工具方法已经足够。**
