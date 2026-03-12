# 更新日志

本文档记录近期关键变更。每条记录固定包含三部分：

- 更新了什么
- 对应文档
- 对应代码位置

## 2026-03-12

### `2026-03-12T17:20:00+08:00` `fix: execute triple-quoted python_repl inputs`

更新了什么

- 修复 `python_repl` 对三引号包裹代码的处理
- 当模型输出 `Action Input: ''' ... '''` 或 `\"\"\" ... \"\"\"` 时，工具现在会正确解包并执行代码
- 新增 `python_repl` 输入规范化回归测试
- 全量测试通过：`pytest -q` -> `48 passed in 1.13s`

对应文档

- `docs/UPDATE_LOG.md`

对应代码位置

- `modules/tools.py`
- `tests/test_tools.py`

### `2026-03-12T17:03:15+08:00` `feat: expose web trace and generalize direct routing`

更新了什么

- 为 Agent 新增结构化运行 trace，包含每轮 `Action / Observation / Tool Spec / Final Result`
- Web 控制台的 `POST /api/chat` 现在返回 trace，前端页面可以直接展示完整中间过程
- 将“直接技能路由”从硬编码数学工具扩展为基于 `ToolSpec` 输入约束的通用绑定逻辑
- internalized skill 在工具知识库中改为使用真实函数签名生成输入字段，而不是固定的 `user_request`
- 新增控制台回归测试和 trace 回归测试
- 全量测试通过：`pytest -q` -> `46 passed in 1.76s`

对应文档

- `docs/WEB_CONSOLE.md`
- `docs/UPDATE_LOG.md`

对应代码位置

- `core/agent.py`
- `core/agent_trace.py`
- `core/skill_routing.py`
- `core/tool_lifecycle_runtime.py`
- `apps/web_console/server.py`
- `apps/web_console/static/index.html`
- `modules/tools.py`
- `tests/test_agent_trace.py`
- `tests/test_web_console.py`

### `2026-03-12T16:47:56+08:00` `feat: stabilize small-model tool routing and loop guard`

更新了什么

- 重写 Agent 系统提示词，明确三种合法输出：`Action`、`tool_spec` JSON、`Final Answer`
- 新增确定性技能路由，对“直接调用现有工具、只返回结果”这类请求走快速路径
- 新增循环保护，检测重复响应和重复工具执行，避免小模型陷入低价值死循环
- 为 `calc_sum_n / calc_lcm / fibonacci` 增加轻量语义打分，降低同分误选概率
- 全量测试通过：`pytest -q` -> `43 passed in 1.32s`

对应文档

- `docs/UPDATE_LOG.md`

对应代码位置

- `core/agent.py`
- `core/agent_prompt_builder.py`
- `core/loop_guard.py`
- `core/skill_routing.py`
- `skills/selector.py`
- `config/settings.py`
- `tests/test_agent_trace.py`

### `2026-03-12T15:53:13+08:00` `refactor: split agent prompt and tool runtime`

更新了什么

- 将主协调器中与提示词构建相关的逻辑拆到 `AgentPromptBuilder`
- 将工具生命周期处理拆到 `ToolLifecycleRuntime`
- 缩短 `core/agent.py`，减少单文件复杂度，便于继续按职责拆分

对应文档

- `docs/UPDATE_LOG.md`
- `docs/ENTRYPOINTS.md`

对应代码位置

- `core/agent.py`
- `core/agent_prompt_builder.py`
- `core/tool_lifecycle_runtime.py`

### `2026-03-12T15:38:01+08:00` `feat: promote registered tools and document entrypoints`

更新了什么

- 打通 `ToolRegistry -> SkillManager` 晋升桥接
- 固定程序入口、Web 入口、测试入口
- 补充文档索引和测试矩阵，减少入口分散问题

对应文档

- `docs/ENTRYPOINTS.md`
- `docs/TEST_MATRIX.md`
- `docs/DOCS_INDEX.md`
- `README.md`

对应代码位置

- `core/agent.py`
- `skills/tool_registry.py`
- `skills/tool_contracts.py`
- `config/settings.py`
- `scripts/run_tests.py`
- `tests/test_agent_trace.py`

### `2026-03-12T15:27:41+08:00` `feat: persist tool registry and promotion history`

更新了什么

- 新增 `ToolRegistry`，将契约和执行记录持久化
- 将 `ToolSpec` 执行结果接入晋升策略
- 为候选工具和正式技能之间的转换建立基础数据结构

对应文档

- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`
- `docs/TEST_MATRIX.md`
- `docs/ENTRYPOINTS.md`

对应代码位置

- `skills/tool_registry.py`
- `skills/tool_contracts.py`
- `skills/tool_promotion.py`
- `core/agent.py`
- `tests/test_agent_trace.py`
- `tests/test_tool_lifecycle.py`

### `2026-03-12T15:16:37+08:00` `feat: compact loop context and repair tool specs`

更新了什么

- 增加 `[Execution Brief]` 和 `[Compressed Loop History]`
- 支持不完整 `ToolSpec` 自动升级到 teacher 修复
- 将修复后的契约重新接回主循环

对应文档

- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`
- `docs/UPDATE_LOG.md`

对应代码位置

- `core/context_compactor.py`
- `core/agent.py`
- `config/settings.py`
- `tests/test_agent_trace.py`

### `2026-03-12T15:08:31+08:00` `feat: close tool-spec loop and stabilize pytest`

更新了什么

- 固定 `pytest` 临时目录，解决 Windows 权限问题
- 增加 `ToolLifecycleParser`
- 打通 `ToolSpec -> teacher -> 修复后继续执行` 的第一圈闭环

对应文档

- `docs/TEST_MATRIX.md`

对应代码位置

- `pytest.ini`
- `tests/conftest.py`
- `skills/tool_parser.py`
- `core/agent.py`
- `tests/test_agent_trace.py`

### `2026-03-12T14:55:56+08:00` `feat: scaffold tool lifecycle architecture`

更新了什么

- 建立 `ToolSpec`、`TeacherRequest`、`ToolExecutionRecord` 等核心结构
- 拆出 discovery / builder / escalation / promotion 四类职责
- 为后续自动内化和项目级复用预留扩展点

对应文档

- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`

对应代码位置

- `skills/tool_contracts.py`
- `skills/tool_discovery.py`
- `skills/tool_builder.py`
- `skills/tool_escalation.py`
- `skills/tool_promotion.py`
- `tests/test_tool_lifecycle.py`
