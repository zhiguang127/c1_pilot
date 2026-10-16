# 独立人工适用性标注

状态 `PENDING_HUMAN_ANNOTATION`；真实 A/B/C 提交均为 0。尚无已完成的独立真实练习或正式校准。模板的 human_attestation=false、status=draft 不能进入 Gold；代码测试里的声明不能算真实评审。

A0 继续使用 P1 原发布与原盲评包，不生成或覆盖其材料。`import-gold --stage a0` 调用 P1 的原身份/证据/逻辑验证后，仅投影逐知识适用性；不把 priority、best_set、比较对或旧 Qwen 标签导入监督。只因优先级分歧而尚未裁决的案例，不阻止双方一致的适用性判断进入独立投影；适用性分歧须由 C 裁决。

A1 独立发布 `a1-v1`，双份包在 `local/review-a1-v1/{A,B}/`；协调人映射在 `private/`。A/B 各 48 张 HTML 卡和空 JSONL 模板，各 1,248 对。随机案例顺序与每例候选顺序独立，卡片不显示原 case/subject/knowledge ID、模型结果、检索分数、旧标签或分组理由。只发给评审自己的文件夹，不发整个仓库或 private。相似序列可能仍使评审识别同人，随机化不保证完全消除此风险。

卡片附原始 42 日记录、单位字段名、已知背景、质量限制、候选正文和来源，模板另存为提交版本，不能改空模板。引用：`d29.sleep_minutes`、`context.population`、`C1.observable_conditions.0`。缺失/null 和不能生理解释的 RHR=0 不作已知个人证据。至少一名主评审与 C 需有相关健康知识审查能力；使用 P1 人员登记的资格/人类/独立性校验，真实身份与实际独立性仍由协调人核实。

每个候选独立填写：

- `topic_relevance`：related / not_related / uncertain。
- `applicability`：applicable / not_applicable / insufficient_information。
- `condition_judgments`：每个来源条件恰好一次，`condition_id`、satisfied / violated / unknown / not_applicable_to_condition、observations、rationale。必须解释 N/A 的条件前提，不把 unknown 自动变 violated。
- `observations`、`conditions`、`missing_information`、`rationale`：明确观测时段、个人基线、必要条件与未记录背景。
- `source_scope_disputed`：来源或草案条件有实质争议时 true，暂停该对 Gold；不能强制转成不适用。

general education 与 narrower claim 的前提不同。条件中“需要症状才能声称损害”不能自动解释为“没有症状记录，教育知识必不适用”。条件草案和正文冲突时应记录争议，而非自行创造必要条件、数值阈值或医学机制。

A/B 锁定独立提交后，协调人按语义字段查找分歧；C 使用 A 卡片编号与原始 A/B 记录，填写完整同结构裁决，增加 `reviewer_id="C"`、`reviewed_reviewers=["A","B"]`。C 时间不得早于任一主评审提交；修订保留新文件与新版本。意见一致也不证明临床正确。A1 需要同时比较主题、适用性、来源争议和逐条件状态，不能只按最终标签忽略条件分歧。

导入拒绝空白、重复、错版本、未知引用、缺失观测被引用、漏条件、错误类别及非独立身份声明。不强制存在适用候选。Gold 独立存放 `local/gold/` 并冻结 provenance 与源文件 SHA；模型 predictions 在 `local/runs/`。未解决分歧或来源争议保留 unresolved，部分覆盖不得描述成全量正式 Gold。

证据引用存在性由软件检查；是否正确理解时间、缺测、设备算法和适用条件仍需人工审查。Missing-Condition Error Rate 和失败机制归因没有人工记录时保持 null。
