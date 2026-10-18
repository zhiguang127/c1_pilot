# 实际执行记录

**补充阶段已完成：** 用户明确提供指定模型配置后，凭据通过用户绑定 DPAPI 写在仓库外，未回显或提交明文。真正运行 TrialGPT 原匹配函数、三种 PHA 架构与 DataScienceAgent 官方样例；同一真实案例的六方法 A0、Direct 三视图 E3、真实 E4 组合均得到输出。最终计量 107 请求，另有早期 PHIA 漏计调用单列；不再宣称 API 费用为零。40/24/87 项最终测试通过。完整最新记录和局限见 [CONTINUATION_READOUT.md](CONTINUATION_READOUT.md)、`results/credential_continuation.json`、`results/reproduction_corrections.json`。下文保留初次交付时的历史过程；它的“缺凭据/未执行”不代表当前状态。

2026-10-18 收尾复验：Experiment A 40/40、P1 24/24、旧 C1 87/87 重新通过；最新日志哈希写入上述聚合记录。最终协议 v11 覆盖全部适配/聚合代码、CLI、配置与测试，保留所有较早协议和推理原始版本。本次收尾没有发出新的模型请求；批量预算与独立人工 Gold 仍待落实。

记录日期：2026-10-16。这里只记录实际完成和实际阻碍，不将 README 的未来命令当成已运行。完整安装/下载/测试 stdout、原始推理和缓存均保存在本机忽略的 local；公开 JSON 保存版本、结果和日志哈希。

## 仓库与数据

1. `git status --short`：开始时干净；本地分支 `research/p1-problem-reidentification`，HEAD `2e904ce`。
2. `git ls-remote origin refs/heads/main` 与 fetch：main 为 `32455e9cf1e9f2406d929c3ef022d14b19204965`。GitHub PR API 确认 #1 已关闭并合并，merged_at=`2026-10-16T09:49:44Z`。
3. `git switch -c research/experiment-a-applicability origin/main`，不修改旧分支或自动合并。
4. 读取 P1 指定的协议、指南、数据审计、readout、README、freeze/cases/knowledge；验证发布 ID 和全部原哈希。原数据不再生成，原 PMData/映射不再下载。
5. 只新增 experiment_a。`audit`：77 个 C1 冻结文件一致；P1 48 例、16 人、240 对。`build-a1` 在任何预测前冻结 26 条不同知识与 1,248 对；生成 A/B 48 卡 + JSON 模板各一套。

## 官方源码、安装与最小运行

使用 Git HTTPS clone 官方 MedCPT / TrialGPT / consumer-health-research（PHA 用 sparse-checkout），记录固定 SHA/License。未编辑上游跟踪源码。

独立 uv 环境：medcpt/trialgpt 为 Python 3.11.14，pha 为 Python 3.12.8。三份实际安装锁文件在 configs。对 MedCPT/TrialGPT 作者 requirements 执行 dry-run 解析，分别因旧 PyTorch、faiss 包失败。PHA 完整 requirements 安装解析因 Gemma/TensorFlow Text 不支持 Windows 失败；按作者 `--no-deps` 路径安装固定 OneTwo 和需要的依赖，成功导入原 ReAct。

实际 MedCPT 下载命令等价于：

```powershell
research/problem_reidentification/experiment_a/local/envs/medcpt/Scripts/python.exe -m research.problem_reidentification.experiment_a download-medcpt
research/problem_reidentification/experiment_a/local/envs/medcpt/Scripts/python.exe -m research.problem_reidentification.experiment_a reproduce --project medcpt --output research/problem_reidentification/experiment_a/results/medcpt_official_smoke.json
```

三段官方 README Python 示例原文 exec 成功；固定模型快照，检查有限值并保存 shape/数值片段、输入、stdout、耗时和运行版本。`evals/models.py` 的真实类用于后续排名，不是重写同名模拟器。

TrialGPT 实际导入原 TrialGPT.py、运行原 parse_criteria。试运行 secure 包装器时安全凭据路径不存在，进程变量与用户级变量也无凭据；在任何模型 API 请求前停止。没有读取其他项目秘密或发送真实健康请求；已取得用户对既有 DashScope 数据传输的明确授权。

PHA 实际命令：

```powershell
# 在官方 personal_health_agent 工作目录，用独立 pha Python：
python -m pytest tests -m 'not e2e' -q
# 在主仓库根目录：
research/problem_reidentification/experiment_a/local/envs/pha/Scripts/python.exe -m research.problem_reidentification.experiment_a reproduce --project pha-offline --output research/problem_reidentification/experiment_a/results/pha_offline_check_v2.json
```

官方测试实际为 124 passed / 15 skipped / 12 deselected；官方合成样例上的真实 Python 计算输出 steps=8156.386301369863、sleep_minutes=417.7972602739726、resting_heart_rate=62.16501457725947。它们是作者样例统计，不是 P1 参与者结果，不是适用性判断。三种架构均没有成功 LLM 推理记录。

## 本地 E1

用同一 src.retrieval.run 入口顺序运行 bm25 / medcpt / medcpt_cross，全部 48 例，CPU，初次设置 torch threads=4。BGE 初次 HF 下载停滞后中止自己的运行进程，不影响已经保存的三项结果；用有重试和 600 秒上限的 curl 从官方不可变提交下载同一权重，实际 173 秒完成，SHA 与 HF LFS etag 匹配后原模型缓存恢复。随后真实 CLI `retrieve --method bge_m3 --output .../local/runs/e1-bge-v1` 完成。

四项结果及实际计时见 BASELINE_RESULTS；192 份排名/查询/模型长度诊断在 `local/runs/*/rankings.jsonl`，逐运行 manifest 保留完整环境和模型元数据。统计查询没有词汇级截断，但三种 dense/cross 全部发生 512 模型 token 截断。

## 标注、评价、预算

实际执行 A1 `packets`，2 套 / 每套 48 卡和 1,248 对空模板。没有人工提交，没有向外联系评审。执行无 Gold 的 `evaluate` 与 `failures`，分别返回 PENDING_HUMAN_ANNOTATION、null 指标和空失败队列。执行 budget，仅产生上界，不消耗付费调用。E2、E3 推理、E4 和 A1 推理未执行，不能报告准确率或失败机制。

模型调用尝试 ledger 仅在真实 API 请求即将发出时增加。软件测试的 SDK double 位于临时目录且退出删除，不属于研究 ledger。当前真实模型 API 请求总数 0、实际费用 0。

## 最终检查与交付

新增 unittest（包括 Gold 导入、源争议保留、过期裁决拒绝、证据/条件引用、三值逻辑、空 Gold、盲法、SDK 缓存/限额/篡改）实际通过；最终数量与日志哈希见 `results/execution_final.json`。

P1 `python -m unittest discover -s research/problem_reidentification/p1/tests -v`：24/24 通过，包含真实浏览器检查。旧 C1 使用原独立 checkenv 执行 `-m unittest discover -s tests -v`：87/87 通过。没有重跑旧模型实验。最后重新验证 77 个 C1 哈希、P1 release、A1 release、三个上游 checkout 和 Git diff；只提交本目录允许公开的文件。

Git 提交和 PR 为此研究分支；PR 不自动合并。当前可交付的是已运行的本地复现/检索证据与待继续的软件/标注工作流，研究状态仍未完成。
