# 失败分析状态

**没有可靠 Gold，因此没有已确认的研究错误或失败机制。** 六类错误计数均为 null，不能把未标注、缺 API 凭据、解析器测试、查询截断或未来的模型分歧当作错误标签。

已观察到的工程/有效性限制：历史依赖在当前 Windows 上不可原样解析；模型凭据缺失；dense 查询全部有 tokenizer 截断；知识条件是旧机器草案且一些 required_context 只限制更窄的主张；恢复状态近邻覆盖不足。这些是后续实验设计必须处理的事实，尚不证明现有强基线无法解决个人适用性。

`failures` CLI 在有独立人工 Gold 后生成私人审查队列，保留成功和错误、原预测和原始证据路径、Gold、方法及候选，并留空人工 attribution/alternative_explanation/repair_checks。六类归因是 Retrieval、Temporal Reasoning、Condition Matching、Missing Information、Knowledge Scope、Annotation Ambiguity；不能仅凭最终标签差异自动判断哪一类。

人工需检查原始观测存在性、正确时间范围、基线/当前区分、缺测与设备质量、来源条件范围，并分别记录统计补充、Prompt、TrialGPT-style、PHA 工具与 PHA+TrialGPT-style 是否修复。没有执行这些对照时，不能宣称失败稳定，也不能挑选看似支持假设的案例。

当前失败队列为空，`gold_verified_errors=null`；没有“新算法机制缺陷”的案例展示。
