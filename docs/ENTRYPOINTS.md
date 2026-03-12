# 程序入口与测试入口

本文档固定仓库的运行入口和测试入口，避免部署到 IPC、Windows 开发机、5070Ti 主机后再去翻代码确认启动方式。

## 主程序入口

### 1. CLI 对话入口

- 入口文件：`main.py`
- 入口函数：`main()`
- 启动命令：

```bash
python main.py
```

- 作用：
  - 启动命令行交互式 CoALA Agent
  - 适合本地直接验证 Agent 主流程

## Web Console 入口

### 2. IPC Web Console

- 入口文件：`apps/web_console/server.py`
- 入口函数：`main()`
- 启动命令：

```bash
python apps/web_console/server.py
```

- 容器入口：

```bash
docker compose -f docker-compose.ipc.yml up -d coala-web
```

- 作用：
  - 提供轻量 Web 聊天与技能检查界面
  - 适合 IPC 现场运行和远程检查

## 推理链路入口

### 3. 本地异步网关

- 入口文件：`scripts/local_async_gateway.py`
- 入口函数：`main()`
- 作用：
  - 解决本地模型长响应或同步接口不稳定问题
  - 作为网络/推理链路层的一部分，不属于 Agent 外层逻辑

### 4. 云端 397B 服务

- 入口文件：`scripts/cloud_397b_service.py`
- 入口函数：`main()`
- 作用：
  - 远程大模型服务层
  - 用于 teacher / fallback / 高复杂度请求

## 固定测试入口

### 1. 标准入口

- 入口文件：`scripts/run_tests.py`
- 启动命令：

```bash
python scripts/run_tests.py --suite all
```

### 2. 直接 pytest 入口

```bash
pytest -q
```

### 3. 分组入口

```bash
python scripts/run_tests.py --suite agent
python scripts/run_tests.py --suite skills
python scripts/run_tests.py --suite memory
python scripts/run_tests.py --suite llm
```

## 入口边界

- `main.py`：主 CLI 入口
- `apps/web_console/server.py`：Web Console 入口
- `scripts/run_tests.py`：固定测试入口
- `pytest -q`：底层测试执行入口
- `docker-compose.*.yml`：部署入口，不直接承载业务逻辑
