# 官方代码复现审计

审计日期：2026-10-16。三个 checkout 均位于忽略的 `local/upstream/`，未修改跟踪源码；每次加载校验 SHA 和 `git status`。源码、模型、完整日志不提交。许可证原件保留在本机；公共清单记录哈希。

| 项目 | 官方来源与固定提交 | 实际证据 | 严格论文复现 |
|---|---|---|---|
| MedCPT | [NCBI](https://github.com/ncbi/MedCPT), `11e129be74102c98d16a11c310b0b5ce74c1db5e` | 三段官方 README 推理原文实际执行；官方 `evals/models.py` DenseRetriever / CrossEncoder 在真实 P1 上运行 | 历史依赖环境未重现；官方权重和未修改推理代码成功 |
| TrialGPT | [NCBI NLP](https://github.com/ncbi-nlp/TrialGPT), `1b3242cd50c153a9c324661d4a0bd94fc68a4226` | 实际导入 `trialgpt_matching/TrialGPT.py` 并运行作者 `parse_criteria`；没有模型调用 | 否，缺授权端点凭据；不把解析器运行称为条件推理成功 |
| PHA | [Google Health](https://github.com/Google-Health/consumer-health-research/tree/main/personal_health_agent), `3e9d1e4877a54cf81ce8ef34085006952dd19601` | 三架构和 OneTwo ReAct 可导入；官方 Python 工具在作者合成样例上实际计算；官方离线测试 124 passed / 15 skipped / 12 deselected | 否，三架构均未完成真实 LLM 推理 |

MedCPT / TrialGPT 为 NCBI Public Domain Notice；PHA 为 Apache 2.0。完整许可证哈希见 `results/baseline_inventory.json`。模型资产的许可声明和各权重 SHA 在 `results/medcpt_official_smoke.json`；HF 模型卡声明 `other`，不能擅自改写为宽松许可证。

## 已读入口和运行差异

- MedCPT：根 README、retriever/reranker 的训练入口及依赖、evals/models.py。历史 `torch==1.7.1+cu110` 无法由当前 Python/Windows 索引解析。独立 Python 3.11 + Torch 2.6.0 + Transformers 4.49.0；不声称运行了训练、BEIR 全量评测或 PubMed 索引。README Query/Article 输出均为 `[3,768]`，Cross 输出 `[6]`，有限值检查通过。README 代码块原文执行，仅将 `from_pretrained` 解析到官方不可变快照。
- TrialGPT：读取 retrieval 的关键词/混合检索、matching/TrialGPT.py、run_matching.py、ranking 的聚合/排序入口。作者 requirements 中 `faiss==1.8.0` 无法解析；只为匹配入口安装作者 OpenAI 1.30.5、NLTK 3.8.1，并固定 httpx 0.27.2。没有运行作者全量检索/排序，未下载大规模临床试验数据。原文件在 import 时构造 Azure client；包装层用无请求占位构造后显式注入受控合法客户端。此处仍缺凭据，没有成功推理可报告。
- PHA：读取六个 agent 文件、05/06/07 notebook、后端配置与 Python/search 工具。作者完整依赖解析被 OneTwo → Gemma → Windows 不支持的 TensorFlow Text 阻挡；按照其 setup 的 `--no-deps` 做法固定 OneTwo `b13bbf8adf894f42ca42a2a8a8a9bf95db98e03d`，显式安装所需依赖，ReAct 可用。未执行会移除已有 conda 环境的上游 setup.sh。离线测试中的 mock 输出只算软件测试。v1 工具检查未捕获表达式数值，v2 使用显式 print 并保留真实数值；两个记录均保存。

当前进程无 `C1_PILOT_API_KEY`，旧安全凭据路径也不存在。已检查存在性并尝试包装器，**没有发出 API 请求**。未搜索其他项目的秘密、未读取 `.env`、未把密钥写入文件。已获得用户向既有 DashScope 端点传输 P1 伪匿名记录的授权；传输授权不等于已有凭据或已批准付费批量。

## 原始实现与适配边界

| 组件 | 真正复用的源码 | 本实验新增 / 状态 |
|---|---|---|
| MedCPT E1 | 作者的 DenseRetriever.encode_queries/encode_corpus、CrossEncoder.predict | P1 查询表示、96 条知识索引、缓存、统一 ID 和截断日志；已实际运行 |
| TrialGPT-style Applicability Matching | 作者 criterion serializer；官方 `trialgpt_matching` 另有独立 Smoke 入口 | 消费健康任务提示、四种条件状态、缺失不等于不存在、同一次模型调用内来源语义聚合；**尚未执行真实适配推理** |
| PHIA / PHA Parallel / PHA Orchestrator | 对应官方类、真实 dataframe / Python 工具和调度 | 只通过外围输入映射、固定源 search/DataCommons 接口、输出 JSON 要求适配；**尚未验证模型端到端** |
| PHA DS → TrialGPT-style | 官方 DataScienceAgent.query + 逐条件适配层 | 额外分析文本与原数据共同输入、成本分开计；**未执行** |

适配后的 TrialGPT 提示不沿用“病历未提即假定不存在”“尽量少选信息不足”。条件元数据是旧机器审查草案，必要/可选/限制的角色解释也不是人工 Gold。`conditions.py` 支持 all/any/not/optional/if 的三值规则，但**没有将全部旧条件自动编译成 AND，也没有宣称这些 AST 已获人工批准**。当前 TrialGPT-style 采用预定义的来源语义聚合规则，在同一次调用中输出逐条件状态与整体判断；该聚合是 LLM 决策，单独作为适配局限报告。

Native Smoke 使用作者合成样例与原生工具。Controlled A0 使用固定候选正文作为唯一额外 search 结果，DataCommons 明示不可用；原数据科学工具与调度保留。两者分开存放。若将来用 Qwen，属于同模型受控/服务端适配，不能声称 Gemini / GPT-4 论文数值复现。官方源码导入成功或模型返回一段文字都不足以证明架构有效。

原作者源文件不改。工具轨迹、实际执行代码与返回值、模型响应与 token/耗时均在 local；公共报告只导出聚合元数据。费用在没有可核验账单时为 null；本轮实际 API 请求数为 0，因此可核实 API 支出为 0。
