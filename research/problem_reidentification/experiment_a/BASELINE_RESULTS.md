# 实际执行结果：首阶段历史记录

**本页下文保留首阶段结果；凭据配置后的真实官方推理、A0/E3/E4 Smoke 和费用已更新至 [CONTINUATION_READOUT.md](CONTINUATION_READOUT.md)。当前状态是 `PENDING_HUMAN_ANNOTATION`，不再缺模型凭据。** 旧 JSON/失败版本不回写；其中早期 PHIA/Parallel/Orchestrator 状态解释错误见 `results/reproduction_corrections.json`，不可将旧计量零值或诊断回退字符串解释为成功/零成本。

状态：**`PENDING_HUMAN_ANNOTATION_AND_API_CREDENTIAL`**。下表只列真实运行，不提供虚构的研究分数。机器记录：`results/execution_final.json`、`results/reproduction_status.json`。

| 实际运行 | 输入 / 输出 | 运行时间 | 判断边界 |
|---|---|---|---|
| MedCPT 官方 README Smoke | 三个官方模型；Query `[3,768]`、Article `[3,768]`、Cross `[6]` | 见 JSON 原始计时 | 模型真实推理通过；非历史依赖环境 |
| BM25 | 同 48 个 P1 窗口，96 条库，全库排名 | 0.171 秒 | 无适用性分类 |
| MedCPT Dense | 同一查询/库，官方 evals 类，全库排名 | 34.016 秒 | 48/48 查询在模型层被截断 |
| MedCPT Dense → Cross | 同一案例，Dense Top20 后官方 Cross 重排 | 464.078 秒 | 48/48 查询截断；只返回重排池 20 条 |
| BGE-M3 | 复用旧固定配置，同 48 个 P1 窗口与库 | 73.797 秒 | 48/48 查询在模型层被截断 |
| TrialGPT 官方 parser | 作者 parse_criteria，明确的合成软件样例 | 见执行记录 | 不是条件推理；LLM 尚未运行 |
| PHA 官方离线 | 124 passed / 15 skipped / 12 deselected；官方 PHIA Python 执行器在作者合成数据上实际算出均值 | 测试 9.08 秒 | mock 单测不是 Agent 推理；三架构均未完成 LLM Smoke |

E1 的时间是每个 run 的模型加载/缓存/索引与批次推理总墙钟时间，CPU、缓存热度不同，不是严格配对的在线单请求 latency。每例摊销值与依赖版本在本地 manifest；不能把速度差直接归因于算法设计。BM25 无模型 tokenizer 截断；三种 dense/cross 设置均截断，故信息预算并非 token 级等价。Cross pair 长度和每例截断数量保留在私人日志，原始 query/ranking 不提交公开仓库。

BGE 初次 HF 下载停滞后被中止，使用官方固定提交的同一文件通过验证 TLS 的 curl 下载；2,271,145,830 字节，SHA-256 `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38`，与 HF LFS etag 一致后填回缓存，配置与模型未换。

四个 E1 设置各完成 48 份真实排名，共 192 份；同一案例集可比较检索输出。**没有任何 A0 适用性三分类预测可比较**：本机会话和旧 DPAPI 位置均缺凭据，包装器在网络请求前停止，API 请求数 0 / 实际 API 支出 0。Direct、TrialGPT-style、PHIA、Parallel、Orchestrator 和组合的适配代码已备，但端到端未验证；不能以软件测试通过表示这些 Baseline 已成功。

E3 的 current/statistics/full 表示构造与输入边界已验证，没有完成 LLM 对照。E4 没有执行。A1 冻结和盲评包已备，没有模型预测或人工标注。付费批量没有执行，价格和可核实账单均不可用，保守调用上限另列预算 JSON。

人工 Gold 0 对。因此 Macro F1、Precision/Recall、confusion、FAR、Unknown Detection、Missing-Condition Error、证据正确率、Applicability Recall@k 与 nDCG **全部未计算 / null**。未标注知识不当作负例，旧 Qwen 标签不进入评价。不能从任何排名推出适用性判断正确。

新增测试、P1 测试、旧 C1 回归与冻结哈希的最终计数见 `results/execution_final.json`。官方 checkout 仍干净；只在本目录增加文件。详细命令、来源/环境和日志哈希见 [EXECUTION_RECORD.md](EXECUTION_RECORD.md)。
