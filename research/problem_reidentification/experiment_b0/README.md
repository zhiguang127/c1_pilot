# Experiment B0 — mandatory external baseline extension

本目录独立于冻结的 Experiment A/P1。先读 [官方方法审计](SOTA_BASELINE_AUDIT.md) 和 [比较结论](SOTA_COMPARISON.md)。S3a/S3b/S4 仅是内部约束消融；没有独立优先级 Gold，不报告推荐准确率或 SOTA 优势。

## 实际可复查入口

```powershell
python -m research.problem_reidentification.experiment_b0.audit_upstream
python -m unittest discover -s research/problem_reidentification/experiment_b0/tests -t . -v
python -m research.problem_reidentification.experiment_b0.run verify
# 仅对当前固定协议运行；缓存重放不产生新的独立案例。
& research/problem_reidentification/experiment_a/configs/run_secure.ps1 -Environment pha -m research.problem_reidentification.experiment_b0.run run
python -m research.problem_reidentification.experiment_b0.report
```

`audit_upstream` 用于初次获取；已有审计快照时拒绝覆盖。新建机器应 checkout `results/upstream_pins.json` 的 SHA，不能把未来 HEAD 当成本次版本。`configs/freeze.json` 是当前比较代码与计划的冻结，`freeze_v1/v2/v3` 保留工程失败；不得删除它们后重标为一次从未修正的预注册实验。添加报告文件不会改变已冻结的推理代码。

`local/` 保存官方 checkout、环境、所有请求/响应、反馈、tool 查询、失败、旧协议源码和当前结果。原始个人数据、逐候选决定、Silver、人类评审／身份映射和密钥不提交。公开仅含聚合指标与内容哈希；B0 不写入 Experiment A 的任何路径。已有安全 wrapper 只在子进程内加载凭据，不打印密钥。

环境记录在 `configs/cpu-audit.lock.txt`。CPU 审计环境继承了主 Python 的可见包，不是作者原历史环境的严格重建；首次缺依赖、TLS 和入口路径失败保留，不能据其单一退出码断言算法本身不可用。健康 API 运行借用已有 `pha` Python 环境，但所有 B0 模型请求、预算、缓存和输出均写入 B0 自己的目录。

机器报告 `results/comparison.json` 记录所有计划分母、成功/结构失败/执行失败、预算对齐、顺序干预与费用。`EXECUTED` 只代表结构可接受的真实输出；自动引用审计不能证明医学、来源范围或优先级正确。运行时状态若为 `RUNNING_OR_INCOMPLETE`，不得将该快照解释为已完成。
