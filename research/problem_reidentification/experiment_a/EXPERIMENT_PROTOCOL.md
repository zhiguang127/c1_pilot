# Experiment A 协议 v1

日期：2026-10-16；仓库起点为远程 main `32455e9cf1e9f2406d929c3ef022d14b19204965`。本地原分支落后一个合并提交且干净；PR #1 已合并。独立分支 `research/experiment-a-applicability`。不提出 M1/M2、不训练模型、不使用旧 provisional Qwen 标签、不修改 C1/P1。

## 研究对象和判断

Topical Relevance、Personal Applicability、Recommendation Priority 分开。只研究前两者；三分类是 applicable / not_applicable / insufficient_information。缺失背景不证明不存在。source_scope 有争议时暂停实质裁决，不强制适用或不适用，也不强制每例至少有一条适用知识。

A0：原 P1 48 窗口 × 固定 5 条。A1：另行冻结的 6 个主题面板，共 26 条不同知识 × 48 原窗口，独立标注版本；分组和选择代码在任何模型预测前冻结。不得基于模型失败换样本。当前均无人工 Gold。

## E1–E4

| 实验 | 方法 / 输入 | 控制与边界 |
|---|---|---|
| E1 | 原 BM25、原 BGE-M3、官方 MedCPT Dense、Dense Top20 → 官方 Cross | 同一 96 条 title+content、相同确定性统计查询、词汇预算 512。记录每模型实际 token 截断。分数只表示检索相关性，不转换为适用性 |
| E2 | Direct、TrialGPT-style、PHIA、PHA Parallel、PHA Orchestrator | 同一固定候选和完整 42 日数据；先共同最小案例，再在预算允许时扩展。服务端模型、温度、请求/工具预算明确记录 |
| E3 | Direct current / baseline+current statistics / full；与 dataframe agent 对照 | 48 例中按 case_id 排序取同一前缀，不能各方法取不同案例。当前摘要不泄漏基线数值；完整输入不静默截断。统计并非对任意时序条件都充分 |
| E4 | 官方 PHA DataScienceAgent.query → TrialGPT-style | DS 分析与原始记录共同提供给条件匹配；额外调用、工具和 token 单独计量。这是既有组件组合，不称新算法 |

E1 本轮统计查询的词汇预算不等于各 tokenizer 预算；MedCPT evals 原生 query_max_length=512，README 独立 query 示例为 64。不能把这些检索器描述成已经看过未截断完整序列。

方法名为 `TrialGPT-style Applicability Matching`。其逐条件四状态与整体三状态分开；整体聚合规则在适配提示中预定义：核心教育陈述的必要前提受支持、无真实禁忌支持时适用；有观测直接违反必要前提时不适用；其余信息不足。只限定更窄推断的上下文可为 optional；误用/诊断警告是 scope restriction；复合条件的原 AND/OR 文义保留。必要/可选角色本身仍是模型解释，需要独立人工审计，不能宣称符号聚合已有人类确认。当前没有正式获批的逐条 AST；三值 AST 工具只提供能力和软件验证。

## 复现门槛、预算和数据传输

官方源码 clone、SHA/License、独立环境、依赖失败和最小入口必须审计。真实官方 LLM Smoke 未通过时，CLI 拒绝运行对应 TrialGPT/PHA 跨任务适配。空响应、parse failure、导入成功、mock 单测均不能冒充基线成功。Direct 可独立运行。

用户已明确授权 P1 伪匿名记录发送到现有 DashScope；只从环境或本机安全存储取得凭据，不从公开或秘密文件搜索密钥。原生 Azure/Gemini 复现与 Qwen 同模型受控配置分开，基础模型不同必须声明。原生 Smoke 只使用作者合成数据，Controlled 使用固定候选来源替代联网 search、禁用在线 DataCommons；不将两种设置的结果混合。

先本地/离线与最小 Smoke；最多 2 例视为小规模。超过两例需审查价格、调用上限并明确允许批量。每次请求、失败尝试、缓存命中、模型返回名、时间、token 与工具输出记录。没有账单或可靠价格时费用为 null，不能编造“估计实际成本”。本轮未发出 API 请求，实际支出为 0。详细保守调用上限在 `results/budget.json`，不是已发生消耗。

## 标注、评价与不确定性

A0 只投影 P1 人工适用性；优先级标签完全不进入评价。A1 分别记录主题、适用性、每项条件、原始观测、缺失、来源争议。A/B 独立、C 裁决语义分歧，保留原始版本和身份声明；模板不是已招募评审或标签。正式前独立真实练习尚未完成。

分类报告固定三类别 Macro F1、各类别 P/R、混淆矩阵、FAR = Gold 非适用类（含未知）中被预测适用比例、Unknown Recall。解析失败和无预测分母另外公开，不能默默丢弃。Missing-Condition Error 与证据语义/时间正确性须由人工单独审查，不能由有无解释自动推出。

全库适用性标签不完整时，只报告 Judged Pool：已标适用知识的召回分母、Top-k 被标注覆盖、不适用比例、移除未判项后的 pool nDCG；明确不能称全库 Recall。主题标签另行报告，不由适用性代替。未标注项永远不当负例。

16 人是独立参与者层级，48 窗口 / 240 或 1,248 对不是独立用户。只做描述性结论；有足够类别和覆盖时可显式启用按参与者整簇 Bootstrap（默认不开启），仍不声称 16 人支持稳健显著性。没有调参/训练；如后续需要，必须按参与者划分并另冻版本。

## 失败归因与结论规则

只对可靠 Gold 的错误归因：retrieval / temporal reasoning / condition matching / missing information / knowledge scope / annotation ambiguity。队列同时保留成功与错误，归因和替代解释由人工填写；模型分歧不是已知错误。逐项检查统计补充、Prompt、TrialGPT、PHA 工具和简单组合能否修复；能修复的不作新算法动机。

允许现有方法或简单组合已经足够，也允许数据/标注不足。当前证据不能选择任何算法成败结论。协议调整用新版本，不回写已冻结选择，不合并 PR。
