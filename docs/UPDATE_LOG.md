# 更新日志

本文档记录近阶段的重要代码变更。每条记录固定包含三部分：
- 更新了什么
- 对应文档
- 对应代码位置

## 2026-03-12

### `2026-03-12T17:36:43+08:00` `fix: tolerate model style read_file inputs and rebuild web console page`

更新了什么
- `read_file` 兼容模型常见输入格式，例如 `main.py|content`，会自动只取文件路径部分。
- `read_file` 优先按当前项目工作目录查找文件，再回落到 `data/` 目录，避免仓库根目录文件读取失败。
- Web 控制台静态页整体重写为干净 UTF-8，修复右侧栏挤压、长 trace 溢出、不换行和页面文案乱码问题。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `apps/web_console/static/index.html`
- `tests/test_tools.py`

### `2026-03-12T17:26:39+08:00` `fix: stop Action Input before Final Answer`

更新了什么
- 修复 `ReActParser` 会把同一轮回复中的 `Final Answer` 误吞进 `Action Input` 的问题。
- 避免 `python_repl` 执行包含 markdown、解释文本或 emoji 的混合内容，减少语法错误和死循环。
- 补充解析器回归测试。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `core/react_parser.py`
- `tests/test_react_parser.py`

### `2026-03-12T17:18:42+08:00` `perf: make python_repl no-stdout feedback actionable`

更新了什么
- `python_repl` 在执行成功但没有 stdout 时，返回明确提示：如果需要可见结果，请使用 `print(...)`。
- 让小模型在下一轮更容易修正执行方式，而不是继续盲目重复。
- 补充针对无输出场景的回归测试。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `tests/test_tools.py`

### `2026-03-12T17:16:27+08:00` `fix: execute triple-quoted python_repl inputs`

更新了什么
- `python_repl` 现在支持执行 `''' ... '''` 和 `\"\"\" ... \"\"\"` 包裹的代码输入。
- 保持对 ```python fenced block``` 的兼容。
- 修复模型按 ReAct 输出三引号代码时“看起来执行成功，实际上没有运行”的问题。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `tests/test_tools.py`

### `2026-03-12T17:03:15+08:00` `feat: expose web trace and generalize direct routing`

更新了什么
- `POST /api/chat` 现在返回完整 trace：`Action / Observation / Tool Spec / Final Result`。
- Web 控制台新增 trace 展示区，可直接查看候选工具、工具匹配和每轮执行步骤。
- “直接技能路由”从数学工具特判扩展为基于 `ToolSpec` 输入约束的通用路由。
- internalized skill 的输入字段由真实函数签名推导，不再固定为 `user_request`。

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
- `tests/test_agent_trace.py`
- `tests/test_web_console.py`

### `2026-03-12T16:47:56+08:00` `feat: stabilize small-model tool routing and loop guard`

更新了什么
- 收紧小模型提示词格式，强调 `Action`、`Action Input`、`tool_spec`、`Final Answer` 的结构化输出。
- 增加循环保护：重复响应、重复工具执行、重复失败时提前熔断，而不是一直打满 `max_steps`。
- 对高置信候选工具增加确定性路由和快速收尾逻辑。

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
- 将提示词拼装从主 Agent 协调器中拆出到独立模块。
- 将工具生命周期流程拆出到运行时模块，降低 `core/agent.py` 的复杂度。
- 固定主协调器职责：编排而不是堆叠所有实现细节。

对应文档
- `docs/UPDATE_LOG.md`
- `docs/ENTRYPOINTS.md`

对应代码位置
- `core/agent.py`
- `core/agent_prompt_builder.py`
- `core/tool_lifecycle_runtime.py`

### `2026-03-12T15:38:01+08:00` `feat: promote registered tools and document entrypoints`

更新了什么
- 打通 `ToolRegistry -> SkillManager` 的晋升桥接。
- 固化程序入口、测试入口和测试矩阵文档。
- 统一说明哪些入口负责 CLI、Web 控制台和测试执行。

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
- `ToolSpec` 和执行记录开始持久化到注册表。
- 引入晋升策略，区分 episode、project、global 三类工具阶段。
- 为后续“完成一次任务后是否内化”为正式技能铺平数据结构。

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
- 增加 `[Execution Brief]` 和 `[Compressed Loop History]`，缓解小模型上下文不足和遗忘当前目标的问题。
- 支持 teacher 修复 `ToolSpec` 后自动回到主流程继续执行。
- 为闭环工具生命周期补上上下文压缩与契约修复能力。

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
- 固化仓库内测试临时目录，修复 Windows 下 `pytest` 临时目录权限问题。
- 新增 `ToolSpec` 解析器，将模型输出从文本提示推进到结构化契约。
- 打通 `ToolSpec -> teacher -> 回到主流程` 的第一轮闭环。

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
- 初始化 `ToolSpec`、`TeacherRequest`、`ToolExecutionRecord` 等核心数据结构。
- 拆出 discovery、builder、escalation、promotion 等职责模块。
- 建立“小模型优先，大模型兜底，成功后内化”的架构骨架。

对应文档
- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`

对应代码位置
- `skills/tool_contracts.py`
- `skills/tool_discovery.py`
- `skills/tool_builder.py`
- `skills/tool_escalation.py`
- `skills/tool_promotion.py`
- `tests/test_tool_lifecycle.py`
