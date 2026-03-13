# 更新日志

记录格式固定为三段：
- 更新了什么
- 对应文档
- 对应代码位置

## 2026-03-12

### `2026-03-12T15:53:13+08:00` `refactor: split agent prompt and tool runtime`

更新了什么
- 将主协调器拆分为提示词构建和工具生命周期运行时，降低 `core/agent.py` 的复杂度。
- 明确主程序入口和模块边界，避免后续继续在单文件中堆积逻辑。

对应文档
- `docs/ENTRYPOINTS.md`
- `docs/UPDATE_LOG.md`

对应代码位置
- `core/agent.py`
- `core/agent_prompt_builder.py`
- `core/tool_lifecycle_runtime.py`

### `2026-03-12T16:47:56+08:00` `feat: stabilize small-model tool routing and loop guard`

更新了什么
- 增加小模型循环保护，提前终止重复响应和重复工具循环。
- 强化直接工具路由，减少明显任务还要依赖自由 ReAct 收尾的情况。

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

### `2026-03-12T17:03:15+08:00` `feat: expose web trace and generalize direct routing`

更新了什么
- Web 控制台开始返回结构化 trace。
- trace 中可观察 `Action / Observation / Tool Spec / Final Result`。
- 直接路由从特定数学工具扩展为基于 `ToolSpec` 的通用路由。

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

### `2026-03-12T17:16:27+08:00` `fix: execute triple-quoted python_repl inputs`

更新了什么
- `python_repl` 开始正确执行三引号和 fenced code block 包裹的代码片段。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `tests/test_tools.py`

### `2026-03-12T17:18:42+08:00` `perf: make python_repl no-stdout feedback actionable`

更新了什么
- `python_repl` 在无 stdout 时返回更可操作的提示，鼓励模型使用 `print(...)` 暴露中间结果。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `tests/test_tools.py`

### `2026-03-12T17:26:39+08:00` `fix: stop Action Input before Final Answer`

更新了什么
- `ReActParser` 在解析 `Action Input` 时遇到 `Final Answer:` 会停止，避免最终答复污染工具输入。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `core/react_parser.py`
- `tests/test_react_parser.py`

### `2026-03-12T17:36:43+08:00` `fix: tolerate model style read_file inputs and rebuild web console page`

更新了什么
- `read_file` 兼容模型常见的 `main.py|content` 风格输入。
- 重建 Web 控制台静态页，修正布局溢出与 trace 展示问题。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `apps/web_console/static/index.html`
- `tests/test_tools.py`

## 2026-03-13

### `2026-03-13T10:20:33+08:00` `fix: sanitize leaked react inputs for small models`

更新了什么
- 修正小模型把 `assistant:`、`user:`、新一轮 `Action:` 泄漏进工具输入的问题。
- `python_repl` 对转义换行和缩进的处理更稳，减少语法噪声。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `core/react_parser.py`
- `modules/tools.py`
- `tests/test_react_parser.py`
- `tests/test_tools.py`

### `2026-03-13T10:41:53+08:00` `feat: add deterministic http route extraction tool`

更新了什么
- 新增确定性内置工具 `extract_http_routes`，将 HTTP API 路由提取从现场写 Python 代码改为货架式调用。
- 接入直接路由链路，降低小模型在项目扫描任务上的格式不稳定性。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `core/tool_lifecycle_runtime.py`
- `core/skill_routing.py`
- `tests/test_tools.py`
- `tests/test_agent_trace.py`

### `2026-03-13T10:58:00+08:00` `fix: improve cjk tool matching and safer python repl escaping`

更新了什么
- 工具发现支持 CJK n-gram，提高中文任务对内置工具的命中率。
- `python_repl` 对字符串字面量中的 `\\n` 和 `\\t` 处理更安全。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `modules/tools.py`
- `skills/tool_discovery.py`
- `tests/test_tools.py`
- `tests/test_tool_lifecycle.py`

### `2026-03-13T11:06:40+08:00` `feat: add skill workbench before internalization`

更新了什么
- 新增 `SkillWorkbench`，在技能正式内化前执行隔离校验。
- workbench 当前会检查语法、函数存在性、函数名一致性和必需参数签名。

对应文档
- `docs/UPDATE_LOG.md`

对应代码位置
- `skills/workbench.py`
- `skills/contracts.py`
- `core/tool_lifecycle_runtime.py`
- `tests/test_skill_workbench.py`
- `tests/test_agent_trace.py`

### `2026-03-13T12:20:00+08:00` `feat: add rl decision-layer scaffolding`

更新了什么
- 新增 RL 决策层脚手架，用于从 trace 中导出离线样本、训练轻量策略并在运行时给出旁路建议。
- RL 当前只做建议，不直接接管主路由，目标是先积累观测数据再决定是否接管。
- Web trace 会记录一条 `RL Policy Suggestion`，便于在控制台中观察策略建议是否合理。

对应文档
- `docs/UPDATE_LOG.md`
- `docs/RL_DECISION_LAYER.md`

对应代码位置
- `rl/__init__.py`
- `rl/contracts.py`
- `rl/decision_dataset.py`
- `rl/policy.py`
- `rl/runtime_router.py`
- `scripts/export_rl_dataset.py`
- `scripts/run_tests.py`
- `core/agent.py`
- `tests/test_rl.py`

### `2026-03-13T12:48:00+08:00` `feat: add gated rl runtime routing`

更新了什么
- 将 RL 建议接成一个默认关闭的运行时门控。
- `direct_tool` 高置信建议现在可以直接接管工具路由。
- `build_tool / ask_teacher` 高置信建议会写入执行简报，作为小模型的强约束提示，而不是直接重写整个主循环。

对应文档
- `docs/UPDATE_LOG.md`
- `docs/RL_DECISION_LAYER.md`

对应代码位置
- `config/settings.py`
- `core/agent.py`
- `core/skill_routing.py`
- `tests/test_agent_trace.py`

### `2026-03-13T13:18:00+08:00` `feat: add built-in document summary tool`

更新了什么
- 新增 `summarize_documents` 内置工具，用于读取单个文件或固定目录下的文档并输出确定性摘要。
- 支持的主格式包括：文本、Markdown、JSON/YAML、PDF、DOCX、XLSX。
- 解析逻辑被拆到独立模块，避免继续扩大 `modules/tools.py`。
- 目录摘要支持聚合多个文件并输出整体 Markdown 摘要。

对应文档
- `docs/UPDATE_LOG.md`
- `docs/DOCUMENT_SUMMARY_TOOL.md`

对应代码位置
- `modules/document_summary.py`
- `modules/tools.py`
- `core/tool_lifecycle_runtime.py`
- `requirements.txt`
- `tests/test_tools.py`
- `tests/test_tool_lifecycle.py`

### `2026-03-13T13:42:00+08:00` `feat: add global and semantic document summary modes`

更新了什么
- `summarize_documents` 新增 `global` 作用域，用于输出目录级整体摘要。
- 新增第二阶段工具 `summarize_documents_semantic`，基于已压缩的文件摘要再做主题和全局总结。
- 仍保持 built-in 形态，不把原始大文档直接塞进小模型上下文。

对应文档
- `docs/UPDATE_LOG.md`
- `docs/DOCUMENT_SUMMARY_TOOL.md`

对应代码位置
- `modules/document_summary.py`
- `modules/tools.py`
- `core/tool_lifecycle_runtime.py`
- `tests/test_tools.py`
- `tests/test_tool_lifecycle.py`

### `2026-03-13T14:05:00+08:00` `feat: add document auto-route and web upload debug entry`

更新了什么
- 为文档摘要工具增加显式自动路由规则，避免继续只靠模糊匹配分数。
- Web 控制台新增调试上传入口，文件会保存到受控目录 `data/web_uploads/`，用于测试文档摘要工具。

对应文档
- `docs/UPDATE_LOG.md`
- `docs/DOCUMENT_SUMMARY_TOOL.md`

对应代码位置
- `core/skill_routing.py`
- `apps/web_console/server.py`
- `apps/web_console/static/index.html`
- `tests/test_web_console.py`
