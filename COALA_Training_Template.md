# COALA 自学习智能体训练方案（SOP）

- 版本：v1.2（增强修订版）
- 适用对象：小参数模型（1.5B/7B）驱动的任务型、工具型、记忆增强 Agent
- 核心理念：SFT 建立基线 + DPO 优化偏好 + 局部 RL 强化决策 + Teacher 模型兜底

## 1. 项目目标与边界

### 1.1 业务目标
- 核心指标：在固定算力下，将任务综合成功率从 `A%` 提升到 `B%`。
- 效率指标：平均推理步数下降 `X%`，Token 消耗降低 `Y%`。
- 记忆指标：长期记忆检索命中率提升 `Z%`，记忆冗余度下降。

### 1.2 非目标（Non-Goals）
- 不做底座模型的大规模预训练（Pre-training）。
- 不做全链路端到端 PPO（避免语言崩坏和高训练方差）。
- 不做无限制的开放域闲聊优化（聚焦垂域任务）。

### 1.3 系统约束
- 模型规格：`TODO`（例如 `Qwen2.5-1.5B` / `Llama-3-8B`）。
- 上下文限制：`TODO` tokens。
- 延迟预算：首字延迟 `< TODO ms`，端到端 `P95 < TODO s`。

## 2. 总体流程架构

采用 `Teacher-Guided SFT -> Preference Optimization -> Local RL` 三阶段闭环：
1. 数据冷启动（Teacher Distillation）：利用强模型生成高质量轨迹，解决小模型冷启动能力不足。
2. 阶段 A（SFT）：固化解题模式，规范决策轨迹与工具调用格式。
3. 阶段 B（DPO/IPO）：利用同任务多解差异，训练模型识别优劣。
4. 阶段 C（Local RL）：仅对关键决策点（记忆读写、工具触发）进行低方差强化学习。

## 3. 训练数据生产标准

### 3.1 任务池定义
- 来源：线上真实日志（脱敏） + 合成困难样本。
- 分桶策略：
  - `T1`：简单问答（无工具）
  - `T2`：多步工具链（Tool Chain）
  - `T3`：长短期记忆交互（Memory I/O）
  - `T4`：异常处理与重规划（Error Recovery）

### 3.2 多解采样与 Teacher 兜底（Candidate Generation）
对每个 prompt 执行以下逻辑：
1. Student 采样：当前模型生成 `K` 个候选解（建议 `K=4~8`，`temperature=0.8`）。
2. 自动打分：计算每个候选解的 `R_total`。
3. Teacher 兜底：
  - 若 `max(R_total) < threshold`（即小模型全军覆没），调用 Teacher 模型生成一条金标准轨迹。
  - 将该轨迹标记为 `source: teacher_distilled`，加入 SFT 正样本池。

### 3.3 打分器（Reward / Scorer）设计

总分公式：

```text
R_total = w_task*R_task + w_format*R_format + w_cost*R_cost + w_memory*R_memory + w_safety*R_safety
```

子项定义：
- `R_task (0~1)`：任务是否解决（核心项）。
- `R_format (0/1)`：结构化输出可解析且字段完整。
- `R_cost (<=0)`：步数、Token、工具调用、时延惩罚。
- `R_memory (-1~1)`：记忆操作准确性与长期收益。
- `R_safety (-1~1)`：安全、合规、越权、幻觉惩罚。

硬约束（建议强制）：
- 若触发严重安全违规，`R_total = 0`（或封顶为极低值），避免 reward hacking。

### 3.4 数据落盘格式（JSONL）
要求记录结构化决策痕迹，避免强制存储完整思维链。

```json
{
  "task_id": "uuid",
  "trace_id": "trace_uuid",
  "input": "用户指令",
  "trajectory": [
    {
      "step": 1,
      "plan": "先检索记忆库",
      "action": "search_memory",
      "action_input": {"query": "会议记录", "time": "yesterday"},
      "observation": "...",
      "rationale_short": "查询历史记录后再回答"
    }
  ],
  "output": "最终回复",
  "scores": {
    "total": 0.85,
    "task": 1.0,
    "format": 1.0,
    "cost": -0.15,
    "memory": 0.10,
    "safety": 0.90
  },
  "meta": {
    "source": "teacher_distilled",
    "model_version": "v1.1"
  }
}
```

## 4. 三阶段训练详解

### 4.1 阶段 A：SFT（决策轨迹与规范化）
- 输入：`source=teacher_distilled` 样本 + `source=self_generated` 且 `R_total` 高的 Top-1 样本。
- 目标：Next Token Prediction。
- 关键点：
  - 训练 loss 重点关注 `plan/action/action_input` 段（可局部加权）。
  - 强化“先计划后行动”的行为模式，而非依赖显式长思维链。
- 退出条件：格式合法率 `>98%`，离线任务成功率达到 Baseline。

### 4.2 阶段 B：偏好优化（DPO/IPO）
- 样本构建：
  - `chosen`：高分回答（或 Teacher 回答）。
  - `rejected`：低分回答（格式错误、死循环、幻觉、步骤冗余）。
- 入池约束：
  - `score(chosen) - score(rejected) > delta`（建议 `delta=0.2`）。
  - 通过质量过滤（例如输出可解析、关键字段完整）。
  - 通过双评审一致性检查（规则评审 + Judge 模型评审一致）再入池。
- 目标：让模型偏向更优解，减少冗余步骤和幻觉。
- 退出条件：Pairwise Accuracy `>65%`（保留集验证）。

### 4.3 阶段 C：局部 RL（决策层优化）
- 优化范围：仅优化 Gate 决策，不做全参数自由生成优化（或冻结大部分层）。
- 动作空间（Discrete Actions）：
  - `Memory_Gate`: `[skip, write_fact, write_preference]`
  - `Tool_Gate`: `[call_tool, answer_directly, ask_user]`
- 算法：Contextual Bandit 或 REINFORCE with baseline。
- 优势：收敛更快、资源消耗更低、可解释性更强。

## 5. 训练循环（Loop）

1. 采样：从任务池按桶采样 batch。
2. 生成：当前策略生成候选，必要时触发 Teacher 兜底。
3. 打分：执行 Reward Function。
4. 构建数据集：
  - 成功轨迹 -> SFT pool
  - 优劣对 -> DPO pool
  - 决策日志 -> RL pool
5. 训练：按 `A -> B -> C` 顺序更新模型。
6. Gate Check：在固定验证集评估，通过后再发布。

## 6. 面向记忆的 Reward 细化（含异步反馈）

记忆奖励具有滞后性，需要显式信用分配。

### 6.1 实时奖励（Immediate Reward）
- 格式检查：写入结构是否正确。
- 查重惩罚：若写入与向量库相似度 `>0.95`，给予冗余惩罚。
- 安全检查：越权写入或高风险内容写入直接负分。

### 6.2 异步奖励（Delayed Reward Pipeline）
建立每日跑批任务，回溯计算：
- 命中奖励 `R_hit`：`T+N` 天内被命中且显著提升任务成功率。
- 致幻惩罚：被召回后被用户或规则判定错误，给予重罚。

信用分配（必须实现）：
- 日志字段：`trace_id`, `memory_id`, `write_ts`, `first_touch_ts`, `reuse_count`。
- 归因规则：按时间衰减和最近触发优先分配奖励，防止误奖历史脏记忆。

## 7. 评测与防作弊（Anti-Hacking）

### 7.1 核心指标
- Success Rate（SR）
- Pass@1
- Memory Precision
- Tool Success Rate
- P95 Latency
- Cost per Task

### 7.2 防 Reward Hacking 检查（必做）
- 长度-分数相关性：检查 `Length` 与 `Reward` 的 Pearson 系数。若 `>0.7`，警惕凑字数骗分。
- 安全拒答率：防止模型为避免犯错而对困难任务全部拒答。
- 工具调用循环率：监控同一工具连续同参调用比例。

## 8. 最小可执行版本（MVP）实施路径

### Week 1：基础设施
- 定义 log schema，确保线上日志包含 `trace_id/action/plan`。
- 开发 rule-based scorer。

### Week 2：数据冷启动
- 筛选 `500~1000` 条典型任务。
- 跑通 Teacher Distillation，生成金标准样本。
- 执行 Stage A（SFT），确保格式正确率 `>95%`。

### Week 3：偏好对齐
- 基于 SFT 模型生成多解（`K=4`）。
- 构建 DPO 数据集并执行 Stage B。
- 重点优化无效步骤与无效工具调用。

### Week 4：记忆门控上线
- 部署简单 Contextual Bandit 控制记忆写入开关。
- 接入异步 reward 回溯流水线。

## 9. 配置文件模板（config.yaml）

```yaml
project:
  name: COALA_Agent_v1
  base_model: "Qwen2.5-1.5B-Instruct"

data_pipeline:
  generation:
    num_candidates: 4
    temperature: 0.8
    teacher_fallback_threshold: 0.4
    teacher_model: "gpt-4o"

  format_requirements:
    force_structured_trace: true
    allow_full_chain_of_thought_storage: false

scoring:
  weights:
    task_success: 0.45
    format_compliance: 0.15
    efficiency_cost: 0.15
    memory_accuracy: 0.10
    safety: 0.15

  hard_constraints:
    safety_violation_zero_total: true

  anti_hacking:
    max_length_penalty: true
    repetition_penalty: true

training:
  stage_a_sft:
    epochs: 2
    learning_rate: 2e-5
  stage_b_dpo:
    beta: 0.1
    learning_rate: 5e-7
    min_score_gap_delta: 0.2
    require_dual_judge_agreement: true
  stage_c_rl:
    policy_type: "discrete_gate_only"
    algorithm: "contextual_bandit"

evaluation:
  window_days: 7
  by_bucket: true
  gates:
    min_success_rate: 0.85
    max_p95_latency_ms: 1500
    max_cost_increase_pct: 10
    max_safety_regression_pct: 0

release:
  rollout_percentages: [5, 20, 50, 100]
  rollback_if:
    success_drop_pct: 3
    p95_latency_rise_pct: 15
    safety_incidents_gt: 0
```

## 10. 实施检查清单（Checklist）

- [ ] 任务池分桶完成，评测集冻结。
- [ ] 候选采样与打分日志可回放。
- [ ] SFT、DPO、RL 三类数据池分离管理。
- [ ] 记忆回溯归因字段已上线（`trace_id/memory_id/write_ts/first_touch_ts`）。
- [ ] 防 reward hacking 监控已接入。
- [ ] 发布门槛与回滚规则已在 A/B 平台验证。
