# Experiment A：个人健康知识适用性审计

当前状态：**`PENDING_HUMAN_ANNOTATION`**。凭据已通过仓库外的用户绑定 DPAPI 配置；真实官方推理和同一案例的受控判断已继续执行。最新结果、费用和限制见 [CONTINUATION_READOUT.md](CONTINUATION_READOUT.md) 与 `results/credential_continuation.json`。这是工程与 Smoke 验证，不是已完成的科研结论。

已运行：官方 MedCPT 三个编码器的 README 推理、真实 P1 数据上的本地检索、TrialGPT 原匹配函数，以及 PHIA、PHA Parallel、PHA Orchestrator 的真实模型/工具执行。后三者以同一 Qwen 配置做服务端适配，原论文基础模型和历史环境未严格复现。未用假响应、旧 Qwen 标签或测试夹具替代；没有人工 Gold。实际状态见 [BASELINE_RESULTS.md](BASELINE_RESULTS.md)、[REPRODUCTION_AUDIT.md](REPRODUCTION_AUDIT.md) 和 `results/`。

P1 的 48 个窗口 / 16 人 / 240 个固定候选组合直接只读复用。A1 另行冻结 6 组、26 条不同知识、1,248 个唯一组合；没有新增个人数据或人工 Gold。所有个人记录、模型输出、工具轨迹、人工提交和盲评卡位于被 Git 忽略的 `local/`。

## 安装与来源

在仓库根目录运行；需要 Git、uv、Python 3.11/3.12。三个官方仓库的 URL、SHA 和许可证哈希在 `results/baseline_inventory.json`。不提交源码副本和权重。

```powershell
$a = 'research/problem_reidentification/experiment_a'
powershell -ExecutionPolicy Bypass -File "$a/configs/setup.ps1"
$py = "$a/local/envs/medcpt/Scripts/python.exe"
$pha = "$a/local/envs/pha/Scripts/python.exe"
python -m research.problem_reidentification.experiment_a --help
```

依赖锁定是本机**兼容运行环境**；不是作者历史环境。PHA 使用作者 setup 中的 OneTwo `--no-deps` 路径，未安装不参与本任务的 Gemma/TensorFlow 全套依赖。详见复现审计。旧 C1、P1 的环境不修改。

## 完整命令示例

输出版本已存在时命令拒绝覆盖；请改为新版本路径。下面 `*-next` 均表示新输出。

```powershell
python -m research.problem_reidentification.experiment_a audit --output "$a/results/input-audit-next.json"
python -m research.problem_reidentification.experiment_a check-baselines --output "$a/results/inventory-next.json"
& $py -m research.problem_reidentification.experiment_a download-medcpt
& $py -m research.problem_reidentification.experiment_a reproduce --project medcpt --output "$a/results/medcpt-smoke-next.json"
& $pha -m research.problem_reidentification.experiment_a reproduce --project pha-offline --output "$a/results/pha-offline-next.json"

# 在安全环境中配置 C1_PILOT_API_KEY；不要粘贴到代码或聊天。
# 包装器也支持已有的用户绑定 DPAPI 凭据，且不打印、记录或持久化明文密钥。
& "$a/configs/run_secure.ps1" trialgpt -m research.problem_reidentification.experiment_a reproduce --project trialgpt --output "$a/results/trialgpt_official_smoke.json"
foreach ($architecture in @('phia','pha_parallel','pha_orchestrator')) {
    & "$a/configs/run_secure.ps1" pha -m research.problem_reidentification.experiment_a reproduce --project $architecture --output "$a/results/${architecture}_official_smoke-next.json"
}
# 当前已通过的官方报告由 configs/active_baselines.json 指定；新报告须人工审查后更新该映射。
# 修改任何冻结的输入/适配代码后创建新的 protocol_freeze，不要回写现有 manifest。

# 本地检索。HF_HOME 只作用于当前 shell；首次会下载约 2.27 GB 的 BGE 权重。
$env:HF_HOME = Join-Path (Get-Location) "$a/local/hf-general"
foreach ($method in @('bm25','bge_m3','medcpt','medcpt_cross')) {
    & $py -m research.problem_reidentification.experiment_a retrieve --method $method --limit 48 --output "$a/local/runs/e1-$method-next"
}

# 统一 A0 小规模执行；六个方法名见 --help。
# 官方复现未通过的方法会在任何真实数据请求之前被拒绝。
& "$a/configs/run_secure.ps1" pha -m research.problem_reidentification.experiment_a smoke --method direct --limit 1 --mode full --max-calls 1 --external-authorized --output "$a/local/runs/a0-direct-next"
& "$a/configs/run_secure.ps1" pha -m research.problem_reidentification.experiment_a run-a0 --method trialgpt_style --limit 1 --mode full --max-calls 5 --external-authorized --output "$a/local/runs/a0-trialgpt-next"
& "$a/configs/run_secure.ps1" pha -m research.problem_reidentification.experiment_a run-a0 --method pha_orchestrator --limit 1 --mode full --max-calls 12 --external-authorized --output "$a/local/runs/a0-pha-next"
& "$a/configs/run_secure.ps1" pha -m research.problem_reidentification.experiment_a run-a0 --method pha_ds_trialgpt --limit 1 --mode full --max-calls 8 --external-authorized --output "$a/local/runs/a0-combination-next"

# E3：对同一候选、同一案例分别使用 current / statistics / full。
& "$a/configs/run_secure.ps1" pha -m research.problem_reidentification.experiment_a run-a0 --method direct --limit 1 --mode current --max-calls 1 --external-authorized --output "$a/local/runs/e3-current-next"
& "$a/configs/run_secure.ps1" pha -m research.problem_reidentification.experiment_a run-a0 --method direct --limit 1 --mode statistics --max-calls 1 --external-authorized --output "$a/local/runs/e3-statistics-next"

python -m research.problem_reidentification.experiment_a budget --output "$a/results/budget-next.json"
# 超过两例需人工核对价格、调用上限和预算后显式添加 --batch-authorized；本轮未执行付费批量。

# A1 已有 a1-v1，不得覆盖。重建必须新版本；不按模型错误更换候选。
python -m research.problem_reidentification.experiment_a build-a1 --output "$a/data/releases/a1-next"
python -m research.problem_reidentification.experiment_a packets --stage a1 --release "$a/data/releases/a1-v1" --output "$a/local/review-a1-next"

# A0 导入 P1 原始人工双评，只投影适用性，不使用优先级监督。
python -m research.problem_reidentification.experiment_a import-gold --stage a0 --packets-path research/problem_reidentification/p1/local/review-v2 --roster research/problem_reidentification/p1/local/roster.json --a research/problem_reidentification/p1/local/a-v1.jsonl --b research/problem_reidentification/p1/local/b-v1.jsonl --adjudications research/problem_reidentification/p1/local/c-v1.jsonl --output "$a/local/gold/a0-v1"

# A1：独立的人员登记、原始提交及裁决。没有分歧时可省略 --adjudications。
python -m research.problem_reidentification.experiment_a import-gold --stage a1 --packets-path "$a/local/review-a1-v1" --roster "$a/local/roster-a1.json" --a "$a/local/submissions/a1-A.jsonl" --b "$a/local/submissions/a1-B.jsonl" --adjudications "$a/local/submissions/a1-C.jsonl" --output "$a/local/gold/a1-v1"

# 没有 Gold：输出 null 指标和 PENDING_HUMAN_ANNOTATION。
python -m research.problem_reidentification.experiment_a evaluate --output "$a/results/evaluation-next.json"
# 有独立人工 Gold 后：
python -m research.problem_reidentification.experiment_a evaluate --predictions "$a/local/runs/a0-direct-next/predictions.jsonl" --gold-dir "$a/local/gold/a0-v1" --bootstrap 1000 --output "$a/local/evaluation-a0-v1.json"
python -m research.problem_reidentification.experiment_a evaluate-retrieval --predictions "$a/local/runs/e1-bm25-v1/rankings.jsonl" --gold-dir "$a/local/gold/a0-v1" --output "$a/local/retrieval-evaluation-v1.json"
python -m research.problem_reidentification.experiment_a failures --predictions "$a/local/runs/a0-direct-next/predictions.jsonl" --gold-dir "$a/local/gold/a0-v1" --output "$a/local/failure-review-v1.json"
python -m research.problem_reidentification.experiment_a summarize --output "$a/results/execution-next.json"
```

从中断的 LLM 请求恢复时重用同一输出目录；请求缓存校验精确输入和输出哈希，失败请求也占调用预算。已完成的预测文件拒绝覆盖。人工 Gold 独立冻结，不能用预测自动生成。报告导出仅允许聚合元数据。

## 测试与下一步

```powershell
& $pha -m unittest discover -s "$a/tests" -v
python -m unittest discover -s research/problem_reidentification/p1/tests -v
research/problem_reidentification/p1/local/checkenv/Scripts/python.exe -m unittest discover -s tests -v
```

离线测试里的 synthetic fixture、SDK test double 和人类声明只验证软件，绝不进入实验结果。下一步最少需要：人工检查共同案例的真实输出与证据；确认付费批量预算；取得独立人工双评与裁决。没有这些证据，不能声称现有方法存在稳定失败或需要新算法。Native/Controlled、缓存重放、解析通过与证据正确性分别报告；历史失败版本不删除。
