# COALA 项目执行 TODO（v1）

- 更新时间：2026-03-05
- 目标：4 周内跑通“多解打分 + SFT + DPO + 记忆门控 RL”最小闭环。

## P0（本周必须完成）

- [x] `trace_id` 贯穿主链路
  - 文件：`core/agent.py`, `memory/vector_store.py`
  - 验收：每次 `search/add` 都能在日志里看到同一个 `trace_id`。

- [x] `vector_store` 增加结构化返回
  - 文件：`memory/vector_store.py`
  - 验收：`search()` 返回 `documents/memory_ids/distances/query_id`。

- [x] 增加 memory 事件日志落盘
  - 文件：`memory/vector_store.py`, `config/settings.py`
  - 验收：生成 `data/logs/memory_events/YYYY-MM-DD.jsonl`，包含 `memory_write/memory_search` 事件。

- [x] 规则打分器 v0
  - 文件：新建 `core/scorer.py`（或 `modules/scorer.py`）
  - 验收：能输出 `R_task/R_format/R_cost/R_memory/R_safety/R_total`。

- [x] 固定评测集冻结
  - 文件：`data/eval/*.jsonl`
  - 验收：至少 200 条，覆盖 T1~T4，每桶不低于 30 条。

## P1（第 2-3 周）

- [ ] Teacher Distillation 数据冷启动
  - 文件：新建 `scripts/generate_teacher_data.py`
  - 验收：生成 500~1000 条 `source=teacher_distilled` 样本。

- [ ] SFT 数据构建流水线
  - 文件：新建 `scripts/build_sft_dataset.py`
  - 验收：同任务仅保留 Top-1/Top-2 高分轨迹，格式合法率 > 98%。

- [ ] DPO 数据构建流水线
  - 文件：新建 `scripts/build_dpo_pairs.py`
  - 验收：`score_gap >= 0.2` 且双评审一致性过滤生效。

- [ ] 防 reward hacking 监控
  - 文件：新建 `scripts/reward_audit.py`
  - 验收：输出长度-分数相关性、拒答率、工具循环率日报。

## P2（第 4 周）

- [ ] 记忆延迟奖励回溯
  - 文件：新建 `scripts/build_memory_rewards.py`
  - 验收：基于 `memory_feedback` 产出 `memory_reward_daily.jsonl`。

- [ ] Contextual Bandit（仅门控）
  - 文件：新建 `core/memory_gate_policy.py`
  - 验收：动作空间仅 `skip/write_fact/write_preference`，可在线热切换。

- [ ] A/B 发布与回滚策略接入
  - 文件：部署配置
  - 验收：支持 5% -> 20% -> 50% -> 100%，触发规则自动回滚。

## 技术债 TODO

- [ ] 修复全仓库乱码注释（编码统一 UTF-8）。
- [ ] 为 `vector_store.py` 增加单元测试（写入、检索、去重、日志）。
- [ ] 把 `print` 改为统一 logger，便于采集和检索。

## 指标 TODO（上线前必须明确）

- [ ] `min_success_rate`：`TODO`
- [ ] `max_p95_latency_ms`：`TODO`
- [ ] `max_cost_increase_pct`：`TODO`
- [ ] `max_safety_regression_pct`：`TODO`

## 本周建议执行顺序

1. 先做 `trace_id + memory 日志`。
2. 再做 `scorer v0 + 评测集冻结`。
3. 接着跑 `teacher data + SFT`。
4. 最后再加 `DPO + memory gate bandit`。

## 架构参考（仅方法借鉴）

- [x] 已沉淀小参数模型参考原则：`docs/SMALL_MODEL_AGENT_REFERENCE_GUIDE.md`
- [ ] 按参考原则落地 `s03/s06`（计划阶段 + 上下文压缩）
- [ ] 按参考原则落地 `s07`（任务图持久化）
