# 基线配置

**最新补充见 [CONTINUATION_READOUT.md](CONTINUATION_READOUT.md)。下表中“待执行”、缺价格和早期输出上限为初次交付时的历史配置。** 当前原生 Smoke 的输出上限为 8192，单次官方 Orchestrator 可用 24 个新请求；Controlled 每次输出上限 4096、每 run 的实际 cap 单独保留。DS 采用作者 8192 默认值，再由受控 transport cap 约束。原作者仅支持的空表列头已提供，不增加任何可选表记录。原生 DuckDuckGo 与 Controlled 固定来源分开。公开价格已核对，实际账单未访问；全量批量未授权或执行。

机器：Windows 11，CPU 推理；设备有 NVIDIA RTX 5060 Ti / 16 GB，本轮未使用 GPU。单独环境和全部安装版本锁在 `configs/{medcpt,trialgpt,pha}.lock.txt`。官方模型哈希与输出在 `results/medcpt_official_smoke.json`，BGE 在 `results/bge_model_asset.json`。

| 方法 | 固定配置 |
|---|---|
| BM25 | 复用旧 `src/retrieval.py`，k1=1.5 / b=0.75，原 tokenizer / ID tie-break |
| BGE-M3 | `BAAI/bge-m3@5617a9f61b028005a4858fdac845db406aefb181`；原 SentenceTransformer pooling、归一化 cosine、无前缀、512 tokens、batch=8、CPU |
| MedCPT Query | `d83a36cc6b8e3a5c5e9d9d6ba156808c1643dcbc` |
| MedCPT Article | `d05a736da4bb84ee4057b7f7999485be6ed85465` |
| MedCPT Cross | `71caf65d4927987813984f54c284405a13fcca49` |
| MedCPT E1 | 原 evals CLS、不归一化 inner product；title/content 成对、512 tokens；Dense Top20 才送 Cross，不混合两类分数 |
| LLM 受控配置（待执行） | 原合法 DashScope base URL，qwen3.8-max、temperature=0、enable_thinking=false；A0 每次输出最多 4096；native Smoke 1024/2048；SDK 重试为 0、单次 timeout=120s |

Qwen 标识不固定供应商权重；必须保存 provider 返回名称和日期。没有原生 Azure/Gemini 凭据，不声称复现论文模型。不同环境中的 SDK 版本是明确的工程差异；E2/E3/E4 使用 pha 统一运行环境以统一 SDK/模型设置。

LLM 包装器是记录/预算/缓存的 transport adapter，不生成假回复。复用旧环境变量名、端点、DPAPI 方式与精确输入哈希缓存原则。旧 API client 的 cache root 固定在 C1 `outputs/llm_calls` 且不能承载官方有工具调度的消息循环，因此未直接复用那个写入路径；所有新缓存都在 Experiment A/local。

输入视图：current 仅当前统计；statistics 包含基线与当前的有效数、缺失/不可用数、均值、中位数、标准差、范围、斜率、邻日差、原始引用和圆钟点统计；full 保留全部 42 行与质量字段。PHA dataframe 日期仅为保留星期顺序的人工分析坐标，不是恢复的原日期，不能推断真实日历/季节/DST。

Native 工具 Smoke 与 Controlled 任务判断分开；Controlled search 只回传已给候选的来源正文，不额外注入医学证据。Tool 日志保留完整执行代码/结果；Token 和共享 case 成本不重复分配到每条知识。精确 cache 命中与实际请求次数分别统计。限额以 `budget.json` 的保守上界为准；当前没有可核实价格，付费批量尚未授权/执行。
