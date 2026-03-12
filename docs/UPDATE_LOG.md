# 更新日志

本文档按提交记录仓库演进，统一写清三件事：

- 更新时间
- 更新了什么
- 对应文档与代码位置

## 2026-03-12

### `2026-03-12T15:53:13+08:00` `refactor: split agent prompt and tool runtime`

更新了什么：

- 将系统提示词拼装从主协调器拆分到独立模块
- 将工具契约处理、teacher 升级、实现代码挂接、晋升逻辑拆到独立运行时模块
- `core/agent.py` 回归编排角色，体量从 800+ 行下降到约 550 行

对应文档：

- `docs/UPDATE_LOG.md`
- `docs/ENTRYPOINTS.md`

对应代码位置：

- `core/agent.py`
- `core/agent_prompt_builder.py`
- `core/tool_lifecycle_runtime.py`

### `2026-03-12T15:38:01+08:00` `feat: promote registered tools and document entrypoints`

更新了什么：

- 增加 `ToolRegistry -> SkillManager` 的晋升桥接
- 达到全局晋升条件且已有实现代码时，自动写入正式 internalized skill
- 固定测试入口为 `scripts/run_tests.py`
- 增加程序入口说明、测试矩阵、文档索引

对应文档：

- `docs/ENTRYPOINTS.md`
- `docs/TEST_MATRIX.md`
- `docs/DOCS_INDEX.md`
- `README.md`

对应代码位置：

- `core/agent.py`
- `skills/tool_registry.py`
- `skills/tool_contracts.py`
- `config/settings.py`
- `scripts/run_tests.py`
- `tests/test_agent_trace.py`

### `2026-03-12T15:27:41+08:00` `feat: persist tool registry and promotion history`

更新了什么：

- 增加持久化 `ToolRegistry`
- 候选 `ToolSpec` 不再只存在于当前回合
- 工具执行结果进入 `ToolPromotionPolicy`
- 工具达到条件后可继续晋升

对应文档：

- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`
- `docs/TEST_MATRIX.md`
- `docs/ENTRYPOINTS.md`

对应代码位置：

- `skills/tool_registry.py`
- `skills/tool_contracts.py`
- `skills/tool_promotion.py`
- `core/agent.py`
- `tests/test_agent_trace.py`
- `tests/test_tool_lifecycle.py`

### `2026-03-12T15:16:37+08:00` `feat: compact loop context and repair tool specs`

更新了什么：

- 增加小模型长回合上下文压缩
- 增加 `[Execution Brief]` 与 `[Compressed Loop History]`
- 大模型修复后的 `ToolSpec` 可以重新进入自动流程

对应文档：

- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`
- `docs/UPDATE_LOG.md`

对应代码位置：

- `core/context_compactor.py`
- `core/agent.py`
- `config/settings.py`
- `tests/test_agent_trace.py`

### `2026-03-12T15:08:31+08:00` `feat: close tool-spec loop and stabilize pytest`

更新了什么：

- 修复 Windows 下 `pytest` 临时目录问题
- 引入 `ToolLifecycleParser`
- 打通“不完整 ToolSpec -> 向大模型升级求助”的第一圈闭环

对应文档：

- `docs/TEST_MATRIX.md`

对应代码位置：

- `pytest.ini`
- `tests/conftest.py`
- `skills/tool_parser.py`
- `core/agent.py`
- `tests/test_agent_trace.py`

### `2026-03-12T14:55:56+08:00` `feat: scaffold tool lifecycle architecture`

更新了什么：

- 引入 `ToolSpec`、`TeacherRequest`、`ToolExecutionRecord`
- 拆分 discovery / builder / escalation / promotion 模块
- 建立小模型工具生命周期骨架

对应文档：

- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`

对应代码位置：

- `skills/tool_contracts.py`
- `skills/tool_discovery.py`
- `skills/tool_builder.py`
- `skills/tool_escalation.py`
- `skills/tool_promotion.py`
- `tests/test_tool_lifecycle.py`

### `2026-03-12T00:00:00+08:00` `fix: clean encoding artifacts and repo defaults`

更新了什么：

- 清理仓库默认项和测试配置噪声
- 收敛本地运行时产物的忽略规则

对应文档：

- `README.md`

对应代码位置：

- `.gitignore`
- `pytest.ini`
- `tests/conftest.py`

### `2026-03-12T00:00:00+08:00` `docs: clarify network boundary and deployment roles`

更新了什么：

- 明确网络/推理链路层与 CoALA 能力层的边界
- 明确 IPC、模型主机、Windows 开发机、阿里云服务器的职责

对应文档：

- `README.md`
- `PROJECT_STRUCTURE.md`
- `docs/IPC_FRP_QUICKSTART.md`
- `docs/LOCAL_ASYNC_GATEWAY.md`
- `docs/WEB_CONSOLE.md`

对应代码位置：

- 以文档为主，无核心运行时代码变更
