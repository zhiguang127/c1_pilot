# Source Condition Audit — QWEN_MAX_SILVER

这是机器来源审计，未获独立人工确认。A0 五条知识均包含在 A1 的 26 条并集中；原冻结正文和条件未改变。逐条件原文、源段落、模型判断理由、提案和验证错误保存在私有 `local/silver_annotations/v1/source_audit/`、`source_audit_canonical/`；修正提案另存 `proposed_conditions_v1.json`，不写回 P1/A1。

## 来源取得与可核验范围

11 个原始 URL 均取得当前页面文本。8 个由本机 TLS 校验 HTTPS 请求获取；CDC 的 3 个直接请求失败，另由网页工具读取同一原始 URL，保留直接失败与网页工具成功的两个版本。访问日期 2026-10-18，最终 URL、时间、段落 ID、HTML/提取文本哈希和获取方式均保留。网页工具回退不是假装本机抓取成功。

条件审计使用确定性的词汇检索证据包（上限 10,500 UTF-8 字节），每个段落保留页面内位置。包内未找到只允许判断“在当前材料中不可核验”，不证明整个来源没有该条件。Google Health 的当前页面与较早 Fitbit/PMData 设备时期的等价性未建立。

## 审计完成度与质量

26 条知识、98 条原条件均有覆盖记录，其中 7 条是模型漏答后由软件明确标记的未解决占位，不能算 Qwen 已作出条件判断。原始模型输出中还有嵌套数组字符串、无法解析的 evidence 字段；可确定性解码的数组不改变判断，不能解析的材料保留原样并作为无已核验引文处理。

模型/未解决占位的 support 分布是 EXPLICIT_SUPPORT 52、GENERAL_ADVICE_ONLY 8、OVERINTERPRETED 2、UNVERIFIABLE 36；这是原始审计分类，**不是 52 条已经人工确认的必要条件**。角色分布为必要前提 25、可选背景 13、强主张范围限制 33、争议 27。

11/26 条知识存在源审计验证问题，共 29 个检查标记（包括漏字段、漏条件、无引文及定位错误，不能直接相加为 29 条不同医学错误）。两处引文在快照中实际存在，但段落编号互换，应归为 WRONG_PARAGRAPH_ID。其余缺引文或未解析材料不靠模型记忆补齐。

| 知识 | 原始来源 | 条件数 | 待复核检查数 | Qwen 漏答数 | 核心支持（机器） |
|---|---|---:|---:|---:|---|
| K005 | [原始页面](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K006 | [原始页面](https://www.nhlbi.nih.gov/health/sleep-deprivation) | 3 | 1 | 0 | EXPLICIT_SUPPORT |
| K016 | [原始页面](https://www.nhs.uk/conditions/insomnia/) | 4 | 2 | 0 | EXPLICIT_SUPPORT |
| K017 | [原始页面](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits) | 3 | 0 | 0 | EXPLICIT_SUPPORT |
| K019 | [原始页面](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K034 | [原始页面](https://www.nhlbi.nih.gov/health/sleep-deprivation/how-much-sleep) | 3 | 3 | 2 | EXPLICIT_SUPPORT |
| K037 | [原始页面](https://www.nhs.uk/conditions/insomnia/) | 4 | 1 | 0 | EXPLICIT_SUPPORT |
| K038 | [原始页面](https://www.nhs.uk/conditions/insomnia/) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K041 | [原始页面](https://www.cdc.gov/physical-activity-basics/guidelines/adults.html) | 4 | 3 | 0 | EXPLICIT_SUPPORT |
| K042 | [原始页面](https://medlineplus.gov/howmuchexercisedoineed.html) | 4 | 3 | 3 | EXPLICIT_SUPPORT |
| K043 | [原始页面](https://www.cdc.gov/physical-activity-basics/guidelines/adults.html) | 4 | 4 | 0 | EXPLICIT_SUPPORT |
| K044 | [原始页面](https://www.cdc.gov/physical-activity-basics/guidelines/adults.html) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K047 | [原始页面](https://www.cdc.gov/physical-activity-basics/guidelines/adults.html) | 4 | 4 | 0 | EXPLICIT_SUPPORT |
| K069 | [原始页面](https://www.cdc.gov/physical-activity-basics/benefits/index.html) | 3 | 0 | 0 | EXPLICIT_SUPPORT |
| K070 | [原始页面](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K071 | [原始页面](https://www.nhlbi.nih.gov/health/sleep-deprivation/healthy-sleep-habits) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K072 | [原始页面](https://www.nhs.uk/conditions/insomnia/) | 4 | 3 | 0 | EXPLICIT_SUPPORT |
| K073 | [原始页面](https://www.cdc.gov/sleep/about/) | 4 | 0 | 0 | UNVERIFIABLE |
| K082 | [原始页面](https://support.google.com/googlehealth/answer/14236917?hl=en) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K083 | [原始页面](https://support.google.com/googlehealth/answer/14237938?hl=en) | 3 | 0 | 0 | EXPLICIT_SUPPORT |
| K086 | [原始页面](https://support.google.com/googlehealth/answer/14237938?hl=en) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K089 | [原始页面](https://support.google.com/googlehealth/answer/14237938?hl=en) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K090 | [原始页面](https://support.google.com/googlehealth/answer/14236917?hl=en) | 4 | 0 | 0 | EXPLICIT_SUPPORT |
| K091 | [原始页面](https://support.google.com/googlehealth/answer/14236917?hl=en) | 4 | 2 | 2 | EXPLICIT_SUPPORT |
| K093 | [原始页面](https://support.google.com/googlehealth/answer/14237938?hl=en) | 4 | 3 | 0 | EXPLICIT_SUPPORT |
| K094 | [原始页面](https://support.google.com/googlehealth/answer/14236407?hl=en) | 3 | 0 | 0 | EXPLICIT_SUPPORT |

## A0 的实质范围风险

K006 的核心是短睡习惯不证明已经适应；不能把一般教育解释为必须先证明个人发生损害。K017 的规律作息建议不自动排斥作息已经规律的人。K041 的一般活动益处与“精确计算指南达标分钟”是两个不同主张，强度信息缺失可能限制后者，不能自动排斥前者。K083 的多日趋势教育不授权诊断或把零心率当生理值。K094 的设备估计睡眠与在床时段区分不等于临床睡眠测量。这些是待验证的范围解释，不是本轮新设的强制适用规则。

总体看，原机器草案的 observable_conditions、required_context 和 non_applicable_conditions 不能直接统一转为排他性的 AND 门槛。来源审计模型也会漏答和错误定位，因此后续个人 Silver 同样需要记录源争议和 review_required。未解决条件不得被包装成已获来源确认；独立人工来源审查仍然必要。
