# 设计交付物验证

验证日期：2026-10-03。验证对象为 design-v1，不是已完成的数据集或实验结果。

## 已实际检查

- 用 PowerShell `Test-Json` 将完整 wearable example 对照 wearable JSON Schema 验证，通过。
- 将文档中的 knowledge draft example 对照 knowledge JSON Schema 验证，通过。
- 将没有正文 / 来源的 draft 改为 verified，确认 schema 拒绝；在 derived_statistics 中加入 stress key，确认 schema 拒绝。
- 用 Python 标准库 json / csv / datetime / statistics 重算 example 的全部 4 组日值统计和 2 组 baseline comparison；与存储值在误差范围内一致。
- 检查 baseline 28 天和 window 14 天的完整连续日期、边界、无重复日期及紧邻关系，合计 42 天。
- 检查 null 与 missing_reasons 对应、低日间覆盖时 steps 缺测、夜间覆盖与睡眠时长；没有把缺测 steps 写成零。
- 检查完整规划表的 C001-C024 唯一性、7 个信息列、每类 6 个、A/B/C 各 8 个。
- 检查 taxonomy 的 8 个 domain、连续不重叠的 K001-K096 ID 配额，合计 96。
- 检查两个 JSONL 无记录、relevance CSV 只有表头、没有模型代码。
- 检查全部本地文档链接可解析、Markdown 代码块成对、项目文档没有个人绝对路径；最终分布再次确认。
- 实际打开并核验 CDC、NHLBI/NIH、AHA、Google Health/Fitbit 的五个来源入口；没有逐条知识正文核验。

## design-v1 时尚未完成（历史记录）

24 条正式原始记录、96 条正文、2304 个独立人工 gold labels、标注一致性、retrieval 实现、任何模型比较结果均未生成或验证。匹配组的实际边际相等、自然噪声、跨日时序、临床 / 健康知识条件真实性，以及模型视图的实际字段隔离，也必须在后续建设 / 执行时验证。

JSON Schema 只检查结构、类型和列出的字段，不执行日期互相比较、所有 metric 的 null/reason 一一对应、质量规则、统计重算或来源真实性判断。当前示例的这些已由独立重算检查，但尚未交付通用 validator 实现。本文档不把示例校验等同于 benchmark 已准备好，也不声称已证明 C1。

## execution-qwen-v1 实际执行验证

以下为完整执行阶段的实测结果，取代上方历史阶段的“尚未完成”状态，但不把 LLM 标签升级为人工 gold。

- 24 条合成 wearable cases、1008 个日记录通过 schema、日期连续性、null/reason、覆盖规则和 derived statistics 重算。
- C003/C005、C009/C011、C016/C018、C021/C023、C022/C024 五组 matched-pair 约束全部通过。
- 96 条知识均有实际权威来源快照、locator、适用条件、访问时间和 provenance；22 个来源被 corpus 使用。Qwen source-only 核验全部通过，但没有人工医学认证。
- judge_a、judge_b、adjudicated 各 2304 条，最终 2304 条 **PROVISIONAL_LLM_GOLD**；当前匿名短编号版本一致，无待裁决值。
- 288 条完整表示，B3 每条恰好五个 query；共享输入哈希通过。实验生成和语义判断使用 qwen3.8-max API，B4 和统计计算为确定性代码。
- BM25 与固定 BGE-M3 各 288 次检索，总计 576 次；同一 corpus/config、top-20、排序和 RRF 重算全部通过。
- 六项指标逐 run 重算一致；192 条 case 汇总、64 条分组汇总、8 条 overall 和全部 matched-pair 分析通过。
- 全部 24 个语义审计、24 个完整失败分析文件以及三份正式报告已产出。语义审计中有 755 条引用核验说明，不确定项没有当作压缩丢失。
- 全部 87 项离线测试通过，src/tests 编译通过，冻结的 77 个输入文件哈希保持一致。
- `outputs/metrics/pilot_validation.json`：`valid=true`、`status=COMPLETE`，没有失败阶段。

研究结论为 **E / inconclusive**，不能据此称 C1 已得到支持。原始失败尝试与运行修复保留在 [EXECUTION_HISTORY.md](reports/EXECUTION_HISTORY.md) 和冻结记录中；没有为支持 C1 改动病例、知识、标签规则或检索参数。
