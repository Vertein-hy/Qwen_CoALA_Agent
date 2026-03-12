# Web Console

用途

- 直接从浏览器测试 Agent 主流程
- 查看每轮运行的结构化 trace
- 检查技能列表、技能日志、记忆日志
- 校验候选技能代码

入口

- 程序入口：[server.py](/f:/temp/Qwen_CoALA_Agent/apps/web_console/server.py)
- 静态页面：[index.html](/f:/temp/Qwen_CoALA_Agent/apps/web_console/static/index.html)

默认地址

- `http://127.0.0.1:7860`

接口

- `GET /api/health`
- `GET /api/skills`
- `GET /api/logs?type=skill&limit=50`
- `GET /api/logs?type=memory&limit=50`
- `POST /api/validate-skill`
- `POST /api/chat`

`POST /api/chat`

请求：

```json
{"message":"请直接调用现有工具计算 1 到 10 的整数和，只返回结果。"}
```

响应：

```json
{
  "trace_id": "tr_xxx",
  "status": "success",
  "route": "deterministic_skill_router",
  "model_name": "tool_spec_direct_route",
  "reply": "55",
  "skill_candidates": [],
  "tool_matches": [],
  "steps": [
    {"kind": "direct_route", "title": "Direct Tool Route", "content": "calc_sum_n(10)", "metadata": {}},
    {"kind": "action", "title": "Action", "content": "calc_sum_n(10)", "metadata": {}},
    {"kind": "observation", "title": "Observation", "content": "55", "metadata": {}},
    {"kind": "final", "title": "Final Result", "content": "55", "metadata": {}}
  ]
}
```

当前 trace 会暴露的步骤

- `direct_route`
- `llm_response`
- `tool_spec`
- `tool_spec_follow_up`
- `action`
- `observation`
- `final`

说明

- Web Console 现在可以直接看到每轮 `Action / Observation / Tool Spec`
- 该 trace 是结构化诊断信息，不包含完整系统 prompt 原文
