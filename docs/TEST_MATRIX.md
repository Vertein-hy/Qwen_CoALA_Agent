# 测试矩阵

本文档明确每个测试文件对应的模块、验证目标和推荐入口。

## 固定测试命令

全量：

```bash
python scripts/run_tests.py --suite all
```

按域执行：

```bash
python scripts/run_tests.py --suite agent
python scripts/run_tests.py --suite skills
python scripts/run_tests.py --suite memory
python scripts/run_tests.py --suite llm
```

## 测试文件与对应项目

| 测试文件 | 对应模块/项目 | 关注点 | 推荐入口 |
| --- | --- | --- | --- |
| `tests/test_agent_trace.py` | `core/agent.py` | Agent 主循环、工具契约、teacher 升级、上下文压缩、晋升桥接 | `--suite agent` |
| `tests/test_react_parser.py` | `core/react_parser.py` | ReAct 解析正确性 | `--suite agent` |
| `tests/test_scorer.py` | `core/scorer.py` | 响应评分与回合结果打分 | `--suite agent` |
| `tests/test_skill_manager.py` | `skills/manager.py` | 技能落盘、去重、验证失败处理 | `--suite skills` |
| `tests/test_skill_runtime_loader.py` | `skills/runtime_loader.py` | 动态加载 internalized skill | `--suite skills` |
| `tests/test_skill_selector.py` | `skills/selector.py` | 技能召回与排序 | `--suite skills` |
| `tests/test_skill_validator.py` | `skills/validator.py` | 代码安全校验与函数规范 | `--suite skills` |
| `tests/test_skill_event_logger.py` | `skills/event_logger.py` | 技能事件日志写入 | `--suite skills` |
| `tests/test_tool_lifecycle.py` | `skills/tool_*` | ToolSpec、ToolRegistry、PromotionPolicy、TeacherRequest | `--suite skills` |
| `tests/test_memory.py` | `memory/*` | 长期记忆检索、写入、trace_id 透传 | `--suite memory` |
| `tests/test_llm.py` | `core/llm_interface.py` | LLM 抽象入口和调用适配 | `--suite llm` |
| `tests/test_openai_compat_fallback.py` | `core/llm_providers.py` | `chat/completions -> completions` 回退 | `--suite llm` |
| `tests/test_router.py` | `core/model_router.py` | 小模型/大模型路由选择 | `--suite llm` |

## 当前固化规则

- 所有自动化测试统一放在 `tests/`
- 统一由 `pytest.ini` 管理默认行为
- 统一由 `tests/conftest.py` 修正 Windows 临时目录问题
- 统一推荐使用 `scripts/run_tests.py` 作为人工执行入口
