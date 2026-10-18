# B0：官方方法、原生执行与跨任务适配审计

审计日期：2026-10-18。独立分支 `research/experiment-b0-sota` 从 Experiment A 提交 `18e2fa2e59e14fd69ef4400bd9d38831128bf0f7` 创建。开始时本地及刷新后的远程均没有 B0 分支、协议或 PR；用户随后明确授权“你自己创建”。S3a/S3b/S4 是本次定义的内部累计约束对照，不能计入论文 SOTA 覆盖。

`NATIVE_REPRODUCED` 在本文仅指**官方原任务最小算法已实际执行**，不代表论文完整结果、全部数据集或统计指标复现。`TASK_ADAPTED` 表示明确更换模型后端、任务、数据或接口；`PAPER_INSPIRED` 表示没有执行原训练或原算法；`BLOCKED` 表示记录的当前运行边界，不证明方法无效。原生与健康任务状态分栏，禁止相互替代。机器证据见 [upstream_pins.json](results/upstream_pins.json)、[native_entrypoints.json](results/native_entrypoints.json)；退出码 0 的 `--help` 也不是算法复现。

逐项目最终双栏状态与实际健康任务接受数见 [baseline_status.json](results/baseline_status.json)；测试与冻结核验见 [validation.json](results/validation.json)。

## 版本与许可

| 方法／官方仓库 | 固定 Commit SHA | 实际许可证据 |
|---|---|---|
| [Self-Refine](https://github.com/madaan/self-refine) | `9a206d41e5d2d0c241bb441f41eeadb945afaa55` | 根目录 `LICENSE`：Apache-2.0 |
| [CRITIC](https://github.com/ZethWang/CRITIC) | `5e865ed78cd1b325cf53b15c7209227760131abf` | README 徽章写 MIT；固定树没有 LICENSE 文件，不能称已获得完整仓库许可文本 |
| [RARR](https://github.com/anthonywchen/RARR) | `51a1a10fe5bada837a368f98cb55288ac5168c9e` | 固定树没有根目录 LICENSE；未推断授权条款 |
| [RE2](https://github.com/zhiyuanc2001/RE2) | `c317f196e34f1a3fbb06d61b48ca924feefbc374` | 无根目录 LICENSE；部分继承的 HF 代码有 Apache-2.0 文件头，不能扩大为整个仓库的许可 |
| [ReRec](https://github.com/jiani-huang/ReRec) | `65b78c5129617a3dcceb2739342e8b5915011dcf` | 无根目录 LICENSE；vendored 组件条款与整个项目许可分开 |
| [RankingSHAP](https://github.com/MariaHeuss/RankingShap) | `36e45975f34ee167261af56c69521d55c998b282` | README 内含 GPL-3.0-or-later 声明；其声称的独立 LICENSE 文件在该固定树中不存在 |
| [TRACE](https://github.com/devUuung/TRACE) | `ab14d963e231f789316a929ae7497f3d1acc674f` | 根目录 `LICENSE`：MIT；数据集条款独立 |
| [PEX-DPO](https://github.com/lingjunzhao/PEX_consistency) | `33f6b73590cf2f4a67235329db4b712420bc9156` | 固定树没有根目录 LICENSE；未推断授权条款 |

第三方 checkout、权重和模型请求不提交。适配器从本地固定源码执行作者定义，没有将第三方实现复制进仓库。缺少根许可文本是审计事实；不据此得出法律结论。

## 逐方法审计

### Self-Refine

[原论文](https://arxiv.org/abs/2303.17651)是推理阶段的 Init → Feedback → Iterate，不需要新训练；同一个模型生成初稿、反馈和修正。官方提供 acronym、对话、代码、数学等任务；acronym 输入标题，输出缩写与多维反馈，依赖 `prompt-lib` 和模型 API，没有专门必须下载的 Self-Refine 权重。

原 CLI `src/acronym/run.py` 的实际首次尝试失败于源码路径/依赖；保留 `local/entrypoint-self_refine.log`。健康适配复用官方 `src/utils.py:Prompt.make_query` 与 Init/Feedback/Iterate 组织，Init 使用共同 B1，运行一次真实反馈和一次真实修正，完整反馈、输入与最终输出均保留。并未把任意“再想想”单次 Prompt 冒充完整复现。跨任务 rubric、统一 JSON、模型与 token cap 都是新增逻辑；实际计数以比较报告为准。健康状态为 `TASK_ADAPTED`，原作者模型及七任务结果未复现。

补充：按作者说明设置 PYTHONPATH 后，原 CLI 的下一阻碍为缺少 `prompt_lib`，对应失败日志也保留。随后在**原缩写任务**上原样执行 `AcronymGenTaskInit`、`AcronymGenFeedback`、`AcronymGenTaskIterate` 三个官方类：3 次真实 Qwen-Max 请求完成 Init→Feedback→Iterate。只替换后端 binding，使用 temperature=0、512-token cap 和显式补全格式 wrapper；它是原任务的 `TASK_ADAPTED` 后端执行，**不是原论文模型的 NATIVE_REPRODUCED**。见 [self_refine_native_domain.json](results/self_refine_native_domain.json)。

### CRITIC

[原论文](https://arxiv.org/abs/2305.11738)使用工具交互验证再修正，原任务为 QA、数学程序和毒性降低；相应工具是搜索、解释器和评分 API，无需训练新的 CRITIC 权重。输入包括问题与已有答案／程序。可复用核心是 `src/qa/critic.py:critic_iter` 的 query → evidence → critique/revision 循环。

原入口尝试在独立环境缺少 `openai` 等依赖；更关键的是该 SHA 的 `src/llms/api.py` 已改为 Zhipu/ChatCompletion，而 QA 控制器仍读取旧 `choices[0]['text']` 结构，不能把当前 HEAD 当成论文历史环境。健康适配通过 AST 原样加载作者 `critic_iter`，注入真实 Qwen 后端、固定工具与任务提示；用 `arg=args` 兼容作者函数内部全局变量拼写，函数体不改。声明式接口把模型实际生成的 query、feedback、final 字段转成作者文本标记。普通版本 2 个阶段，预算对齐版本 3 个阶段，均只有一次最终推荐修正。

原任务精确后端与搜索复现 `BLOCKED`；健康比较名为 **CRITIC-adapted (`TASK_ADAPTED`)**。完整 42 天、质量标记、统计和来源片段对 CRITIC 与所有 ECR 对照完全相同；工具结果没有 Gold、Silver 来源审计或 Oracle。固定 staged 接口与原可变交互策略是适配差异，不能宣称保持了全部原生策略。

### RARR

[原论文](https://arxiv.org/abs/2210.08726)对已有文本做问题生成、检索、agreement gate、局部编辑及证据归因报告；主要目标是证据支持和尽量保留原文，而非优化推荐排序。输入是 claim／可选 context，原接口使用 OpenAI Completion、Bing、passage ranker；没有新训练的必需权重，但 passage ranker 与原 API 需要配置。

原 `run_editor_sequential.py --help` 失败于缺少 `jsonlines`；原完整环境和外部搜索没有执行成功。健康适配实际执行作者 `run_rarr_question_generation`、`run_agreement_gate`、`run_rarr_editor` 及其解析器，设置一轮问题、最多一条证据包、一次编辑；使用真实模型而不是预置 gate。检索改为当前任务允许的完整冻结记录与来源包。`select_evidences` 也执行，但只有一个完整证据包，选择退化为唯一包，未运行原 CrossEncoder 排序；不能称完整原生检索复现。

Editor 只能回传解释和引用；程序保留 Init 的排序、适用性与 priority-identifiable，不把新排序静默加入 RARR。五候选 JSON 编辑上限从原单句 512 调到 2048，是明确的任务接口适配。健康状态 `TASK_ADAPTED`，名称 **RARR-adapted Explanation-only Repair**。本轮没有运行 `RARR + Reranking Adapter`，因此不为它补造结果；未来新增排序修正须另设实验臂及新增逻辑说明。

### RE2

官方代码对应 [WWW 2026 论文](https://doi.org/10.1145/3774904.3792283)。原完整 PDF 的本次获取被站点访问阻止；方法细节以下以固定官方 README、训练配置和 reward 源码为可核查依据，未假称完整读到出版 PDF。代码实现 Pattern Imitation（SFT）后 Pattern Internalization（GRPO），显式 reasoning 后输出推荐；`rewards_one_phase.py` 使用 next-item 命中奖励与格式奖励。它不是只加一个思维链 Prompt。

原数据是 MovieLens 历史／候选／next-item 与生成 reasoning；仓库包含 4516 条 SFT、4480 条 GRPO、564 条验证、565 条测试 JSONL。SFT 配置是 Qwen2.5-7B-Instruct，GRPO 指向本地 SFT checkpoint，7 个 generation、最多 1200 步；评估脚本要求用户填 checkpoint。固定树没有训练后模型权重，也没有在 README 中找到可核验的作者最终 checkpoint 下载项。实际评估入口尝试失败于当前审计环境缺少 `transformers`；更换依赖本身不会产生作者训练后的权重。

完整原生及健康训练复现 `BLOCKED`；B2 精确命名 **RE2-style Reason-then-Recommend Prompting (`PAPER_INSPIRED`)**，只把“先 reasoning 后 recommendation”的任务组织迁移到共同 API 模型，没有执行 RE2 SFT／GRPO，不能标为 RE2 复现。可复用训练器、格式、奖励组织；健康数据构造、可信优先级奖励和部分序关系评估必须另行适配。

### ReRec

[原论文](https://arxiv.org/abs/2604.07851)是推荐推理的强化微调，包含图增强奖励、reasoning-aware advantage 和 curriculum。任务输入为复杂推荐 query、候选／属性图与参考推荐；官方数据接口为 Parquet 的 `prompt`、`reward_model` 及 GEXF 属性图，推理为 `scripts/predict.py` 的 vLLM batch。训练配置使用 Qwen2.5-3B、Ray/FSDP、5 个 rollout、2 GPU；不是本轮 API 提示基线。

当前固定树没有训练后 checkpoint。推理入口实际失败于 Windows 审计环境缺少 `vllm`；官方要求 Linux/CUDA，未在 Windows 强装完整训练栈或假造模型。原生与健康训练为 `BLOCKED`。可复用 rollout/reward/advantage/curriculum 组织；可信健康优先关系、属性图、reward 与数据切分均需要重新定义和训练。没有使用本轮 Silver 标签替代推荐监督。

### RankingSHAP

官方方法为 listwise 特征归因：对冻结评分函数反复掩蔽／替换特征，比较整个排序并估计 Shapley 贡献。输入是 query 的候选特征矩阵、background 分布及可重复查询的评分函数，不输出一个新的最优推荐。官方主实验使用 LETOR/MQ2008、MSLR 与训练后的 ranker；其 notebook 还提供原生合成 talent-search 评分函数。

本次实际运行作者 notebook 的数据／评分函数定义和 `RankingShap.get_query_explanation`，种子 0、`average` query，得到五维归因；不是只打开 notebook 已保存的输出。记录在 `local/rankingshap-native-v1.log`。原生最小算法状态 **`NATIVE_REPRODUCED`**；未运行完整 LETOR 实验、没有宣称其 ground-truth attribution 指标复现。依赖使用 Python 3.12 CPU 兼容环境，偏离作者测试的 Python 3.11，具体版本见 lock。

健康任务直接比较 **`BLOCKED`**：现有 BM25/BGE 检索分数不等于可信健康推荐优先级评分，LLM 生成排序也不是这里已冻结的连续评分接口。没有用 Silver 临时拟合评分器。以后可对事先冻结、有明确输入特征和语义的 ranker 解释，但不能把 attribution 本身当作纠错算法或准确率。

### TRACE

官方 [RecSys 2026 方法](https://doi.org/10.1145/3773078.3831796)对序列推荐做 targeted ranking-aware counterfactual search，目标包括 bring-in / push-out，约束编辑数与模型查询预算。输入为离散 user-item 历史序列及冻结 SASRec/BERT4Rec/GRU4Rec；候选选择与影响位置搜索在 `BeamSearchExplainer`。仓库提供五数据集、15 个实际 checkpoint，而非仅训练脚本。

本次从 GroupLens 下载 MovieLens-100K，使用作者 `data.preprocess` 的 5-core、ID 映射和留二切分，得到 943 用户、1349 item、99287 interaction；使用官方 SASRec checkpoint 执行 `run_explain.py`。参数为 bring-in、目标原 rank 2–50、3 用户、seed 42，TRACE 的 `pacer_lite` 候选和 influence 位置策略。首次缩小为每人 100 query、最多 2 edits 时，3 人均没有有效反事实，Hamming/ΔNLL 为 NaN。随后在**相同三人**上使用作者 10000 query、最多 5 edits 的预算：**3/3 找到有效反事实**，query 分别 1301/10000/7735，edit 数 1/3/2，平均 Hamming=2.0、ΔNLL=0.02636。两次结果均保留，预算不足的零结果不能被解释为方法无效。原生最小算法 **`NATIVE_REPRODUCED`**，仍只有三人一 seed、CPU 环境，不能作完整论文效果复现；日志和 checkpoint/输出哈希见 [native_algorithm_runs.json](results/native_algorithm_runs.json)。

TLS 下载、缺少 `adam_mini` 和 `sympy` 的中间失败全部保留；最终未修改作者跟踪源码。健康任务比较 **`BLOCKED`**：连续生理日记录并不是用户点击／消费的 item 序列；缺少健康知识交互模型与有效编辑语义。把每天包装成“item”再调用 TRACE 会改变算法问题，当前没有这样做。

### PEX-DPO

[原论文](https://arxiv.org/abs/2505.19299)首先量化 prediction–explanation consistency：解释对预测及其相反标签的支持；再按 PEX 构建解释偏好并做 DPO。原任务包含 TripAdvisor/Amazon 的评论真伪分类，不是健康推荐排序；faithfulness 还用 student simulation 检验。训练优化解释一致性不能直接证明预测更正确。

官方 `compute_pex_score.py` 接收 review、prediction、explanation，需能计算标签概率的本地分类模型；README 提供 Google Drive 的 Llama2-13B SFT checkpoint 链接，固定树未包含权重，本次没有下载或验证其几十 GB 内容。完整管线包括 SFT、采样解释、PEX、DPO 和 student。原入口尝试失败于当前环境缺少 `transformers`；没有最终 DPO checkpoint 的本地可运行证明。

原生及健康任务 **`BLOCKED`**。可复用 WoE/PEX 计算、偏好对构建与 DPO；健康适配必须先定义多候选／部分序的预测概率语义、区分“支持模型预测”和“来源证据有效”，并独立评估决策。没有改写成普通 consistency Prompt 后称 PEX-DPO。

## 训练与计算需求：估算，不是已运行 benchmark

| 方法 | 可靠监督／数据前提 | 内存与执行规划 |
|---|---|---|
| RE2 | reasoning + next-item 的 SFT/GRPO 格式；健康需人工裁决的可比较优先对与解释，不强制 ties 成独特 Top-1 | 7B BF16 权重下界约 14 GB；常规全参 Adam 参数/梯度/master/moments 粗计约 112 GB，另加 activation；GRPO 多 rollout/参考模型需额外内存。规划 Linux、多 GPU 分片；先小规模 profile 再报 GPU 小时 |
| ReRec | query、候选图、可信 outcome／优先级与 token reward；属性图不能来自未审核的 Silver 假真值 | 3B BF16 权重下界约 6 GB；常规全参 Adam 粗计 48 GB，另加 rollout/reference/activation。官方脚本 2 GPU，显存型号并非本次实测；不保证单 16 GB GPU 能完整运行 |
| PEX-DPO | 经任务适配的分类／概率模型；解释偏好来自 PEX，决策正确性仍需独立 Gold | 13B BF16 权重下界约 26 GB，全参 Adam 粗计约 208 GB；LoRA/量化可降低但改变配置。还需解释采样与 student 训练，不能只估一次推理 |
| TRACE | 已冻结的序列推荐模型、历史序列、有效 item 编辑域 | 本次 3 用户 CPU smoke 已执行；官方 README 报完整格点单 RTX 5090 约 10 小时、训练另约 4 小时，这是作者估计，不是本机测速 |
| RankingSHAP | 固定 ranker、背景分布、明确的特征替换语义 | CPU smoke 已执行；规模随特征、采样数和评分成本增加；未来应记录实际 scorer query 次数 |

权重与优化器估算使用十进制 GB、约 2 bytes/parameter BF16、约 16 bytes/parameter 常规混合精度 Adam 的工程下界；不含 activation、KV cache、通信、padding 或多个模型副本，不是峰值显存承诺。当前 B0 没有开展新训练，GPU 小时／云费用未实测，不能给出假精确值。

后续正式训练对照必须先获得两位独立人工评审及真实分歧裁决，按参与者划分训练/验证/测试并隔离同人窗口，保留 ties、不可比较与缺测。冻结基础模型、来源、候选、训练预算及早停规则；先在各方法原生任务验证训练／推理，再报告跨任务适配。比较 RE2 SFT+GRPO、ReRec 原 reward/advantage/curriculum、PEX SFT→DPO 与相同训练预算的无约束模型，不能只比较 API Prompt。训练前先做短 profile，按 `steps × measured seconds/step × GPU count` 报时间与成本区间；目前没有所需测量值。

## RecPIE 与创新边界

[RecPIE 原论文](https://arxiv.org/abs/2502.16759)把解释生成与预测交替训练，使用下游推荐 outcome 奖励优化解释。它直接限制“让解释反过来改善推荐就是新贡献”的宽泛主张。本次检查论文页面、正文代码链接和精确名称搜索，没有定位到可信作者官方实现；记录为 Related Work / 后续训练基线候选，**未复现**。同名无关仓库不作为实现证据。

已有工作已经覆盖：先推理后推荐、普通反馈再修正、工具验证再修正、证据归因和文本修复、排序整体特征贡献、排序感知反事实，以及训练阶段的预测—解释一致性与解释反馈改善预测。B0 不能再将这些宽泛目标作为创新。

候选相对的纵向来源约束最多是一个待检验的任务机制假设。只有独立确认的具体推荐错误在同模型、同数据、同工具、对齐预算下仍无法被强已有方法解决，而该约束稳定修复它，才可能支持独立贡献；本轮没有这种 Gold 或结论。
