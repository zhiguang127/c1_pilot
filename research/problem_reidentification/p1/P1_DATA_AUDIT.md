# P1 数据与资源审计

审计日期：2026-10-16；起点 commit：`898c737f796b586cf7f6e40a32e4ca263d3fe9f3`。本轮新增内容均在本目录。原实验不修改、不重新解释为真实数据实验。

## 现有仓库

| 资源 | 实际性质 | P1 复用判断 |
| --- | --- | --- |
| `data/wearable_cases.jsonl` | 24 个确定性合成 case，每例 28+14 天；`src/generate_cases.py` 可重建 | 禁止作为真实案例。可参考字段定义，不复用数值或构造类型 |
| `data/knowledge_items.jsonl` | 96 条教育知识、8 个领域、22 个权威/官方文档 URL；包括适用条件和出处 | 可复用来源、独立短改写与条件；`verified` 不等于人工医学核验 |
| `data/corpus_seed.json`, `data/source_manifest.json`, `data/source_snapshots/` | 源支持锚点和 2026-10-03 原抓取快照 | 复用为可追溯依据，复制五条元数据，不刷新或覆盖旧文件 |
| `data/independent_corpus_review.json`, `data/corpus_verification.json` | 机器/LLM 的来源审查记录 | 只证明已有审查流程，不作为本轮人类审核 |
| `annotations/judge_a.csv`, `judge_b.csv`, `adjudicated.csv`; `data/relevance_labels_provisional.csv` | Qwen 同系列模型的 provisional LLM judgments；24×96 相关性标签 | 禁止作为人工 Gold、P1 优先级或独立人工一致率 |
| `docs/annotation_guideline.md` | 原相关性 0/1/2 规范，明确“不标最终推荐优先级” | 复用证据引用、缺测、盲法原则；不能改名当作 P1 标注 |
| `reports/PILOT_RESULTS.md`, `FAILURE_ANALYSIS.md`, `VALIDITY_NOTES.md` | 合成场景下的检索表现、失败与效度局限，原结论为 inconclusive | 只能说明旧实验边界，不能证明纵向记录具有优先级监督信号 |
| `data/input_freeze.json` | 77 个冻结输入的 SHA-256 | 本轮检查 77/77 一致；旧冻结结果及报告维持原样 |
| 顶层 `wearable_cases.jsonl`, `knowledge_items.jsonl`, `relevance_labels.csv` | 旧 design 的空容器 | 不当作实际数据来源 |

审计也检查了相关本地项目的 PMData/真实基础案例文件名，以及已有 `C1_C2_Methods_Experiments_20261013` 方法材料。发现的是 PMData 计划引用，没有可验证的已有真实基础案例。未解包与此任务无关的项目备份，也不把这次有限查找写成“本机绝无真实数据”。用户随后明确要求自行下载，因此直接使用官方发布。

## 本轮真实数据

原始来源：[PMData 官方 OSF](https://osf.io/vx4bk/)，API 节点 `vx4bk`。数据背景和许可参见[原论文](https://doi.org/10.1145/3339825.3394926)与 [Simula 数据页](https://datasets.simula.no/pmdata/)。本轮通过原始 OSF API 分页列举并下载，未使用 Kaggle/Hugging Face 镜像。原始许可是 CC BY-NC 4.0。

下载 16 名参与者的 93 个 JSON 文件，共 8,937,162 字节。六类目标文件共应有 96 个；3 个在源中不存在：p12 的 RHR、p12 的轻度活动分钟、p13 的 RHR。它们均记录为 `absent_at_source`，不补造。

下载范围是主睡眠、RHR 和四种设备活动分钟。未下载分钟级 steps、原始心率、照片、饮食、PMSys、症状或个体人口学表，避免不必要数据量；本轮不能据未导入的信息作判断。论文报告的成人群体范围作为有出处的背景，个体年龄仍未知。

按事先规则形成 **48 个真实纵向窗口，来自 16 人，每人 3 窗，共 2,016 个日行**。技术排除 0 个，不代表数据完整。窗口内有 50 个日期出现选用字段相同的主睡眠重复导出，已折叠并标记；选用字段冲突 0 个。另有 90 个 RHR=0 源记录，保留数值但标记为不能作生理解释，不能读成零心跳；28 个非零睡眠 infoCode 保留并标记设备质量未知。没有根据健康模式或潜在排序过滤窗口。

| 导入字段 | 缺失日行数 / 2,016 |
| --- | --- |
| 主睡眠时长、在床时间、起止钟点、起始日偏移、日志类型、infoCode（各字段） | 428 |
| RHR | 577 |
| Fitbit 轻度活动分钟 | 162 |
| Fitbit 中度活动分钟 | 36 |
| Fitbit 高度活动分钟 | 36 |
| Fitbit sedentary 分钟 | 36 |

这些是数据覆盖描述，不是适用性、优先级或医学结论。零活动记录和存在日记录不等于已知佩戴时间；覆盖筛选宽松，因此相关性和优先级可能被真实缺失信息限制。

## 知识来源与本轮核查

固定面板五条均通过原冻结文本的支持锚点存在性和哈希检查，并于本轮再次打开其官方链接核对可访问性与支持内容：

| 旧 ID（不发给盲评者） | 主题 | 直接来源 |
| --- | --- | --- |
| K006 | 稳定短睡眠不证明已经适应 | [NHLBI 概述](https://www.nhlbi.nih.gov/health/sleep-deprivation) |
| K017 | 睡眠起止规律 | [NHLBI 睡眠习惯](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits) |
| K041 | 日常活动的一般指导 | [CDC 成年人活动](https://www.cdc.gov/physical-activity-basics/guidelines/adults.html) |
| K083 | 多日 RHR 记录视图 | [Google 官方心率说明](https://support.google.com/googlehealth/answer/14237938?hl=en) |
| K094 | 主睡眠期与估计睡眠时间的区别 | [Google 官方睡眠说明](https://support.google.com/googlehealth/answer/14236407?hl=en) |

本轮在线访问没有覆盖原快照或改写正文，也没有创造五条知识之间的推荐排序。锚点匹配不是语义或临床正确性证明；旧来源审查仍是 LLM provisional review。当前 Google 文档与 2019 年 Fitbit 算法的兼容性、成人一般条件和具体适用性仍需人工评审，不把来源“权威”写成“每个 case 都适用”。

## 可复用与缺口

可复用：真实原记录、可追溯知识正文及条件、原盲法与质量处理经验。不可复用：合成病例数值、旧 Qwen 相关性、旧检索指标、原假设构造类型及预期知识差异。

已备：固定取样、HMAC 伪匿名化、每日缺测/质量标记、不可覆盖发布、双份随机卡片、逐候选/逐对标注、证据引用校验、三人角色校验、分歧队列和无假结果分析。

仍缺：真实的 A/B 两名人工评审、具相关专业背景的 C、正式评审前的独立真实练习与校准记录、全量双评与裁决。此时研究状态只能是 `PREPARED_NOT_ANNOTATED`，不能判断 P1 成立与否。
