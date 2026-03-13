# RL 决策层说明

## 目标

当前强化学习接入点不是“训练整个 Agent 生成 ReAct 文本”，而是优化高层离散决策：

- 是否直接使用现有工具
- 是否进入 `ToolSpec` 构建
- 是否升级到 teacher
- 是否直接结束当前回合

这样做的原因很明确：
- 你当前的主要噪声来自小模型格式不稳定，而不是缺少生成自由度
- 先学“选什么”比直接学“怎么写 ReAct 文本”更稳
- 离线训练样本可以直接来自现有 trace 和事件日志

## 当前组成

### 1. 样本结构

- `rl/contracts.py`
  - `DecisionState`
  - `DecisionAction`
  - `DecisionSample`
  - `PolicySuggestion`

### 2. 数据导出

- `rl/decision_dataset.py`
  - 从 trace 提取离线样本
  - 将执行结果映射为 reward
  - 输出 JSONL 数据集

- `scripts/export_rl_dataset.py`
  - 命令行入口
  - 用法：

```bash
python scripts/export_rl_dataset.py --input data/traces.jsonl --output data/rl_samples.jsonl
```

### 3. 轻量策略

- `rl/policy.py`
  - 目前是线性打分策略
  - 特征包括：
    - `tool_match_count`
    - `top_tool_score`
    - `skill_candidate_count`
    - `top_skill_score`
    - `has_tool_spec`
    - `repeated_tool_error`
    - `current_step_count`
    - `mentions_http_route`

### 4. 运行时桥接

- `rl/runtime_router.py`
  - 将当前上下文转换为 `DecisionState`
  - 生成 `PolicySuggestion`
  - 当前只作为旁路建议，不直接接管主流程

### 5. trace 观测

- `core/agent.py`
  - 在进入主循环前记录一条 `RL Policy Suggestion`
  - 便于在 Web 控制台中观察 RL 策略是否合理

## 当前边界

当前 RL 只做三件事：
- 导出可训练样本
- 生成轻量策略建议
- 把建议暴露到 trace

当前 RL 不做三件事：
- 不替代主路由
- 不在线更新权重
- 不训练底层 LLM 生成文本

## 推荐的下一步

1. 把 trace 长期保存为统一 JSONL 格式
2. 根据真实成功率调整 reward
3. 在 `SkillRouter` 前增加可开关的 RL 决策门
4. 先让 RL 决定“direct_tool / build_tool / ask_teacher”，再考虑更细粒度控制
