# COALA Vector Store 埋点与奖励回溯技术规格

- 版本：v1.0
- 目标：把 `memory/vector_store.py` 从“纯存取组件”升级为“可训练、可归因、可回放”的数据采集与策略优化基础设施。

## 1. 设计目标

1. 支撑 `SFT/DPO/Local-RL` 的统一日志数据源。
2. 能对“写入决策”进行在线与离线评估。
3. 能将延迟奖励回溯到具体 `memory_id` 与具体 `write_action`。
4. 不显著影响线上时延（单次埋点 < 3ms，异步刷盘）。

## 2. 当前代码现状与差距

现状（`memory/vector_store.py`）：
- 仅有 `add(text, metadata=None)` 与 `search(query, n_results=3)`。
- 无 `trace_id`、`memory_id`、`query_id` 级别日志。
- 无检索命中质量和后验反馈机制。

差距：
- 无法构建 `RL pool`。
- 无法做延迟奖励归因。
- 无法做记忆策略消融实验。

## 3. API 改造建议（向后兼容）

建议保留现有方法名，但增加可选上下文参数：

```python
add(
  text: str,
  metadata: dict | None = None,
  trace_id: str | None = None,
  write_reason: str | None = None,
  source: str = "self_generated",
  score_snapshot: dict | None = None,
) -> str  # return memory_id

search(
  query: str,
  n_results: int = 3,
  trace_id: str | None = None,
  query_type: str = "default",
) -> dict
# return {
#   "documents": [...],
#   "memory_ids": [...],
#   "distances": [...],
#   "query_id": "..."
# }
```

说明：
- `add` 返回 `memory_id`，供后续 feedback 与回溯使用。
- `search` 返回结构化结果，不再只返回文本列表。
- 若调用方不传新参数，走默认值，保证旧调用不崩。

## 4. 事件日志 Schema（JSONL）

落盘位置建议：`data/logs/memory_events/YYYY-MM-DD.jsonl`

### 4.1 写入尝试事件 `memory_write`

```json
{
  "event_type": "memory_write",
  "event_ts": "2026-03-05T10:00:00Z",
  "trace_id": "tr_123",
  "memory_id": "mem_abc",
  "source": "self_generated",
  "write_reason": "task_success_summary",
  "text_len": 128,
  "metadata": {"type": "conversation"},
  "dedup_score": 0.12,
  "write_accepted": true,
  "score_snapshot": {"task": 1.0, "memory": 0.2}
}
```

### 4.2 检索事件 `memory_search`

```json
{
  "event_type": "memory_search",
  "event_ts": "2026-03-05T10:00:02Z",
  "trace_id": "tr_123",
  "query_id": "q_789",
  "query": "昨天会议纪要",
  "query_type": "task_context",
  "top_k": 3,
  "hits": [
    {"memory_id": "mem_abc", "rank": 1, "distance": 0.18},
    {"memory_id": "mem_def", "rank": 2, "distance": 0.27}
  ]
}
```

### 4.3 反馈事件 `memory_feedback`

```json
{
  "event_type": "memory_feedback",
  "event_ts": "2026-03-06T04:20:00Z",
  "trace_id": "tr_456",
  "query_id": "q_789",
  "memory_id": "mem_abc",
  "feedback_type": "hit_success",
  "delta_task_score": 0.35,
  "label": "positive"
}
```

## 5. 奖励定义（面向记忆策略）

即时奖励：

```text
R_immediate = +0.1 * write_accepted
            - 0.2 * dedup_penalty
            - 0.5 * unsafe_write
```

延迟奖励：

```text
R_delayed = +1.0 * hit_success
          + 0.5 * delta_task_score
          - 1.0 * wrong_recall
```

总记忆奖励：

```text
R_memory = R_immediate + gamma^dt * R_delayed
```

建议：
- `gamma=0.98`，`dt` 以天为单位。
- 对单条 `memory_id` 做奖励裁剪：`[-1.5, 1.5]`。

## 6. 归因规则（避免误奖）

1. 最近触发优先：同一任务命中多条记忆，优先归因 `rank=1`。
2. 分摊机制：若多条都显著相关，按 `softmax(-distance)` 分摊奖励。
3. 时间衰减：越旧记忆分配越低。
4. 负反馈覆盖：若用户明确“记错了”，对对应 `memory_id` 直接强负奖励。

## 7. 训练数据产出

从日志聚合三类数据：
- `sft_memory_samples.jsonl`：高质量写入/检索轨迹。
- `dpo_memory_pairs.jsonl`：同任务下好写入 vs 坏写入。
- `rl_memory_gate.jsonl`：状态、动作、奖励（bandit）。

bandit 样本字段：

```json
{
  "state": {
    "task_bucket": "T3",
    "query_len": 12,
    "retrieval_hit_rate_7d": 0.42,
    "memory_size": 10234
  },
  "action": "write_fact",
  "reward": 0.37,
  "trace_id": "tr_123"
}
```

## 8. 代码落地步骤（建议顺序）

1. 在 `config/settings.py` 增加日志开关与路径。
2. 在 `memory/vector_store.py` 实现 `_log_event()` 和 schema 序列化。
3. 在 `core/agent.py` 调用 `search/add` 时传入 `trace_id`。
4. 新增离线脚本：`scripts/build_memory_rewards.py`，按天回溯产出奖励。
5. 新增离线脚本：`scripts/export_memory_rl_dataset.py`，导出 bandit 训练集。

## 9. 验收标准

- 日志完整性：`>= 99%` 请求带 `trace_id`。
- 训练可用性：连续 7 天可产出 `rl_memory_gate.jsonl`。
- 性能：埋点开启后 P95 增加不超过 `+30ms`。
- 质量：记忆重复写入率下降 `>= 20%`。

## 10. 风险与规避

- 风险：日志量暴涨。
  - 规避：采样 + 压缩 + 按天归档。
- 风险：错误反馈污染奖励。
  - 规避：反馈置信度阈值 + 人工抽检。
- 风险：策略过度保守不写记忆。
  - 规避：设置最小写入率下限监控。
