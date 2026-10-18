# Qwen-Max Silver 标注协议

本轮所有模型标注、来源审计和语义证据审查均为 **`QWEN_MAX_SILVER`**。不创建 Human Gold，不改原人工导入协议、C1/P1/A1 冻结输入、既有基线预测，不训练模型或设计 M1/M2。最新实测聚合记录由 `results/silver_latest.json` 指向；逐条健康数据与标签只保存在忽略目录 `local/silver_annotations/v1/`。

## 固定输入与顺序

1. 核验旧 C1 77 个哈希、P1 发布及 A1 发布。审计 A0/A1 知识并集 26 条（A0 五条包含其中），不将 A1 原 `source_audit.json` 中的 URL 清单误称为已完成语义核查。
2. 获取 11 个原始来源 URL，保留访问日期、最终 URL、状态、段落 ID 与内容哈希。直接请求失败与网页工具成功获取的快照分别保留。没有取得文本时只可标记不可核验。
3. 逐知识审计原始条件：来源明确支持、只支持一般建议、机器过度解释、无法核验；区分必要前提、可选背景和更强主张的范围限制。每个原条件恰好一次，引用必须确实存在于快照。词汇匹配选取的证据包不保证穷尽页面，未在包中找到不等于来源明确否定。
4. 完成来源审计后，先在旧工程按 case_id 取首例的同一个案例上做两轮 Smoke。标注 Prompt 不接收原基线预测、另一轮标注、旧 Qwen 标签或证据审查结论。
5. 如获得明确预算授权，再从其余参与者中每人固定取一个窗口。排除出现在任何旧 `local/runs/*/predictions.jsonl` 的参与者，按 block、case_id 取最早窗口。选择在本轮模型预测前冻结，15 名参与者、15 窗口、75 个不同案例—知识对、150 条双轮标注。**这只排除了旧适用性 LLM 调试暴露；E1 检索已处理过全部 48 窗口。**

每个窗口均使用原 28 日基线与 14 日当前记录。紧凑列式 JSON 保留全部原指标、日序、星期、phase、缺测、质量标记与已知背景，不含 subject_id。程序检验能逐字段还原 42 行；不截断为摘要。另附程序计算的均值、总体标准差、OLS 日趋势、相邻变化及圆形时钟统计。统计项保留样本数、缺失数与正确时期；统计描述不自动构成医学阈值。

## 两轮隔离、证据与争议

轮 A 采用固定 seed 的候选排列，轮 B 严格反转该排列，保证顺序改变；两个请求均是新对话。记录同模型标签一致率和有效分母，不把一致当作独立共识。默认不运行第三轮，也不以重试替换不喜欢的判断。

输出至少包含 case_id、knowledge_id、三分类、每条件状态/角色/解释、supporting_observations、violated_conditions、missing_information、source_scope_disputed、rationale、annotation_model、label_provenance 和 review_required。

最终 Prompt 为 `qwen-max-silver-prompts-v4`。初期 JSON Object 与首次函数接口 Smoke 的失败版本分别保存，未混入最终两轮一致率。最终首例的 10 条输出通过结构/引用检查，标签为 4/5 一致（80%）；不能把通过软件检查写成标签全一致。阶段快照见 `data/silver_protocol_v*.json`，每次实际请求都保存完整 Prompt 与模型参数，可核对历史版本。

- Unknown 与 Not Applicable 分开。不得推断未记录的症状、疾病、目标、个体年龄、佩戴完整性或经过验证的运动强度。
- 引用采用 `dN.field`、`context.field` 或 `stats.baseline.field.stat` / `stats.current.field.stat`，必须存在且匹配原值与时间范围。
- null 与 RHR=0 只能用于明确的缺测说明，不能作为生理证据。检查不自动把引用缺测位置当成判断错误，需区分引用目的。
- 不把 general education 的可选背景变成必要门槛；不把限定诊断或指南达标推断的条件变成一般教育的排他条件。
- 核心来源有实质争议时须标记 review_required、source_scope_disputed，并保留 insufficient_information。来源审计提案仍是机器解释，不能声称已获人工批准。
- 结构或证据验证失败时保留原返回和标签，增加 accepted=false、validation_errors 与 review_required；不调用另一个模型修标签，不把失败记录混入有效分母。

## 模型、版本、费用与停止条件

独立客户端固定请求 **`qwen-max`**、temperature=0、结构化输出、非流式、SDK max_retries=0；不会套用旧 `qwen3.8-max` governor，也不发送旧模型的 enable_thinking 参数。使用原安全包装器加载仓库外 DPAPI 凭据。返回 model、system_fingerprint（若有）、服务端创建时间、SDK 版本、精确请求/响应哈希、token、结束原因、时间与公开价格估算均记录。滚动别名不是不可变权重快照，服务端只返回别名时不得声称知道精确权重版本。

来源审计采用 JSON Object。验证发现该模式不能保证嵌套类型后，最终个人标注与证据审查改用强制 `record_silver_audit` 函数参数 Schema；它只是结构化返回容器，程序不执行该函数或任意外部工具。最大输出为个人标注 5120、证据审查 4096；一个来源响应截断后有明确记录的 8192 来源重试。Schema 和聊天封装同样纳入上下文与费用预留。

价格核验日期 2026-10-18：[官方 Qwen-Max 页面](https://help.aliyun.com/zh/model-studio/qwen-max)，北京输入/输出/缓存输入每百万 token 分别 ¥2.4 / ¥9.6 / ¥0.48。费用是公开价估算，账单实际金额未知。

初始小规模范围累计上限 ¥5、最多 48 个新请求；包含 26 条来源审计、首例两轮标注、30 条既有预测的盲化审计及有限工程失败。正式扩展前需生成实际输入预算，并明确记录用户授权。持久账本在发请求前按 UTF-8 字节加聊天封装上界和最大输出预留无折扣费用，同时限制请求数；失败、断线或缺 usage 的请求保留预留金额。缓存精确匹配请求并校验响应哈希；缓存重放不算新增独立标注。未知 tokenizer 的字节上界是保守工程限制，不宣称是实测 token。

用户随后明确回复“100块！”，本轮累计上限修订为 **¥100**、最多 96 次新请求，授权记录位于私有预算目录。最终扩展为 30 次逻辑请求，按实际输入及 Schema 预留约 **¥3.44**，只是本轮 15 人 Silver 扩展，不授权旧六方法的全 48 例批量实验。候选与参与者选择没有因标签改变。

扩展中遇到函数参数 JSON 不能解析时，允许最多一次**同一完整请求**的明确格式重试。原失败响应、费用、哈希与重试原因保留；不能因最终标签、模型分歧或内容引用检查失败而重试。每例独立写检查点，单例失败不丢弃其他例；重试仍失败则保留无标签的 unresolved，不编造补齐。源码修改仅涉及恢复/验证流程时，旧模型请求参数与 Prompt 不变，离线重验另存 `validated_labels/`，不修改原输出。

原始首个来源响应出现 null/字符串式 evidence，未用于个人标签。它的原始缓存与异常保留；v2 Prompt 显式要求嵌套 JSON 数组。调整发生在首次个人标注前，不把软件修正当成新的研究样本。后续版本调整逐次保留快照及原因。

## 可复现入口

从仓库根目录运行，模型命令经既有安全包装器：

```powershell
$a = 'research/problem_reidentification/experiment_a'
$py = "$a/local/envs/pha/Scripts/python.exe"
$m = 'research.problem_reidentification.experiment_a.silver'
& $py -m $m prepare
& $py -m $m budget --cap-cny 5 --max-calls 48
& "$a/configs/run_secure.ps1" -Environment pha -m $m source-audit
& "$a/configs/run_secure.ps1" -Environment pha -m $m annotate --scope smoke
& $py -m $m forecast
& "$a/configs/run_secure.ps1" -Environment pha -m $m evidence-audit
# 仅获得明确授权并记录实际授权后，才用 authorize-batch 修订上限，再运行：
# & "$a/configs/run_secure.ps1" -Environment pha -m $m annotate --scope heldout
& $py -m $m revalidate
& $py -m $m format-probe
& $py -m $m summarize
```

相同本地源快照和私有缓存可精确重放；其他机器需另行取得合法私有 P1 记录和源快照。CDC 的直接请求拒绝与网页工具回退不是同一抓取方式；原网页工具快照保存在私有 `sources/web_*.json`，没有这些快照时应诚实报告不可核验，不能补写假证据。CLI 遇到无凭据、预算/上下文超限、未授权批量或未完成来源审计即停止，并保存私有异常。

Silver 独立存储，不写 `local/gold/`。原 `trusted_gold` 仍只接受独立人工双评/裁决 provenance；回归用软件夹具验证 Silver 即使改名为 Gold 文件也会被拒绝。公开结果仅导出预定义聚合字段；原健康记录、逐条预测、方法盲化映射、模型推理和源网页全文不提交。
