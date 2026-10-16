# P1 工作区

本目录独立于冻结的 C1 Pilot。先读 [P1_READOUT.md](P1_READOUT.md)、[P1_PROTOCOL.md](P1_PROTOCOL.md)、[P1_DATA_AUDIT.md](P1_DATA_AUDIT.md) 和 [P1_ANNOTATION_GUIDE.md](P1_ANNOTATION_GUIDE.md)。数据归属和许可见 [NOTICE.md](NOTICE.md)。

本轮材料状态为 `PREPARED_NOT_ANNOTATED`。真实数据已备；人工 A/B/C 尚未招募或产生标签。没有一致率或 P1 结论。

## 已交付目录

```text
data/releases/p1-v2/           冻结的 48 个真实窗口、五条知识、协议、指南、审计和哈希
results/readiness.json        无人工标签的真实状态，研究指标为 null
local/pmdata/                原始 OSF 文件、完整来源清单与原始许可（git 忽略）
local/pseudonym.key          仅本机 HMAC 密钥（git 忽略）
local/mapping-p1-v2.json      原参与者/日期到案例的映射（git 忽略）
local/review-v2/A/           A 的 48 份独立 HTML 卡片、表单、指南和空模板
local/review-v2/B/           B 的独立随机顺序和候选顺序材料
local/review-v2/private/     协调人专用映射和卡片冻结清单
tests/                      明确标记的构造软件夹具；不作为研究数据或标签
```

原始记录和映射不随 Git 提交。公开的派生记录已去掉源 ID 和绝对日期，但仍是可识别性有限的伪匿名数据。每位评审只接收自己的文件夹，不应获得仓库、原始记录、另一评审材料或 private。校准尚未实际完成，需正式标注前安排独立真实练习并记录。

## 执行

在仓库根目录使用 Python 3.11+；P1 运行时仅依赖标准库，不需要 Qwen、GPU 或模型凭据。首次/重建示例（新发布请使用新目录名，禁止覆盖已存在发布）：

```powershell
$p1 = 'research/problem_reidentification/p1'
python -m research.problem_reidentification.p1 download --raw-dir "$p1/local/pmdata"
python -m research.problem_reidentification.p1 prepare --raw-dir "$p1/local/pmdata" --output "$p1/data/releases/p1-v2"
python -m research.problem_reidentification.p1 packets --release "$p1/data/releases/p1-v2" --output "$p1/local/review-v2"
python -m research.problem_reidentification.p1 verify --release "$p1/data/releases/p1-v2" --packets "$p1/local/review-v2"
python -m research.problem_reidentification.p1 analyze --release "$p1/data/releases/p1-v2" --output "$p1/results/readiness.json"
```

仓库中已有 `p1-v2`，不要重跑 prepare 到同一路径；直接 verify，或在另一工作副本中用新版本名构建。新机器需重新生成密钥，伪匿名 ID 会改变；如需完全复现原 ID，须由协调人安全保留原密钥和私有映射。冻结发布本身可直接验证。download 对已完成的下载仅校验并返回，不覆盖原清单/时间；源更新需另一个下载目录。OSF API 分页列出全部参与者，只抓六类所需文件，失败最多重试三次；不绕过 TLS 校验。

## 人工评审及汇总

将 `local/review-v2/roster.template.json` 复制到 `local/roster.json`，由协调人登记实际 A/B/C 的不同匿名 person_id、专业背景、角色、人工与独立性声明。模板不是已招募名单。声明由协调人负责核实；软件无法证明身份或实际独立性。

评审在浏览器打开 HTML 卡片，可查看完整每日数据和来源，再填写页末离线表单、导出 JSON。每人最终导出分别放到 `local/submissions/A/`、`B/`，保留原提交和后续修订为独立版本，不覆盖；一次 collect 的目录中仅放该版每 case 的一个最终导出。

```powershell
python -m research.problem_reidentification.p1 collect --input-dir "$p1/local/submissions/A" --output "$p1/local/a-v1.jsonl"
python -m research.problem_reidentification.p1 collect --input-dir "$p1/local/submissions/B" --output "$p1/local/b-v1.jsonl"
python -m research.problem_reidentification.p1 validate --release "$p1/data/releases/p1-v2" --packets "$p1/local/review-v2" --roster "$p1/local/roster.json" --a "$p1/local/a-v1.jsonl" --b "$p1/local/b-v1.jsonl"
python -m research.problem_reidentification.p1 adjudication-queue --release "$p1/data/releases/p1-v2" --packets "$p1/local/review-v2" --roster "$p1/local/roster.json" --a "$p1/local/a-v1.jsonl" --b "$p1/local/b-v1.jsonl" --output "$p1/local/adjudication-v1"
```

C 的文件夹内有分歧记录、双方卡片和可导出的 C 表单，使用 A 的引用编号；不是要求 C 再盲于两人意见。C 审查全部语义分歧，按实际缺口允许并列/信息不足，不追求强制共识。分歧发生在适用性、优先对、case 判断或最优集合任一处都须处理。理由措辞不同而语义标签一致的原记录仍保留，不自动算标签分歧。

```powershell
python -m research.problem_reidentification.p1 collect --input-dir "$p1/local/submissions/C" --output "$p1/local/c-v1.jsonl"
python -m research.problem_reidentification.p1 analyze --release "$p1/data/releases/p1-v2" --packets "$p1/local/review-v2" --roster "$p1/local/roster.json" --a "$p1/local/a-v1.jsonl" --b "$p1/local/b-v1.jsonl" --adjudications "$p1/local/c-v1.jsonl" --output "$p1/local/analysis-v1.json"
```

若无分歧，最后命令省略 `--adjudications`。缺任一主评审会返回部分标注状态；分歧未裁决会保留 `AWAITING_ADJUDICATION`，最终比例为空。空白、重复、漏 pair、未知引用、null 观测证据、非人工声明、非独立身份、优先环和矛盾并列均被拒绝。没有标签时只生成准备状态，绝不调用 LLM 或生成模拟研究结果。

## 测试

```powershell
python -m unittest discover -s research/problem_reidentification/p1/tests -v
```

核心测试无需第三方库。可选浏览器测试在已安装 Playwright 和可用 Chromium/Windows Edge 时执行，否则明确 skip。本机验证实际运行了浏览器，检查离线填表、动态逐对比较、JSON 下载和后端校验；测试生成的“人工”声明仅是临时构造夹具，退出即删除，不进入研究材料。

协调人可独立核对冻结发布与原始记录（不调用导入器，也不生成标签）：

```powershell
python -m research.problem_reidentification.p1.tests.verify_real_release --release "$p1/data/releases/p1-v2" --raw "$p1/local/pmdata" --mapping "$p1/local/mapping-p1-v2.json" --packets "$p1/local/review-v2" --output "$p1/local/engineering-check-next.json"
```

旧仓库回归需原依赖，本机只在忽略的 `local/checkenv/` 补装原锁定的 tiktoken 0.9.0，未修改原 requirements 或全局 Python。命令与结果见 P1_READOUT。
