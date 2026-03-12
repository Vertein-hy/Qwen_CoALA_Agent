# 文档索引

本文档说明每份文档的作用，避免文档散落后难以判断应该先看哪一份。

## 部署与运行

- `README.md`
  - 仓库总入口
  - 说明整体架构边界、推荐运行模式、核心入口文档

- `PROJECT_STRUCTURE.md`
  - 说明网络链路层与 CoALA 能力层的职责边界

- `docs/ENTRYPOINTS.md`
  - 固定主程序入口、Web Console 入口、测试入口

- `docs/IPC_FRP_QUICKSTART.md`
  - IPC + FRP + 本地模型链路的快速运行说明

- `docs/DOCKER_REMOTE_DEV.md`
  - 外部机器通过 Docker 进行远程开发的方式

- `docs/WEB_CONSOLE.md`
  - IPC 上 Web Console 的启动和使用

## 模型与链路

- `docs/LOCAL_MODEL_SETUP.md`
  - 本地模型服务准备与基本配置

- `docs/LOCAL_ASYNC_GATEWAY.md`
  - 本地异步网关设计和使用方式

- `docs/CLOUD_397B_SERVICE.md`
  - 云端大模型服务的部署和作用

## Tool Lifecycle / Agent 演化

- `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`
  - 小模型优先的工具发现、构建、升级、晋升架构

- `docs/SMALL_MODEL_AGENT_REFERENCE_GUIDE.md`
  - 小模型代理的参考设计与行为约束

## 测试与更新

- `docs/TEST_MATRIX.md`
  - 每个测试文件对应哪个模块、验证什么、怎么跑

- `docs/UPDATE_LOG.md`
  - 每次提交的更新摘要
  - 重点记录：更新了什么、对应文档、对应代码位置

## 数据与镜像分发

- `docs/DEV_BUNDLE_MIRROR_SPEC.md`
  - 开发 bundle 镜像和同步分发的规格说明

## 训练与数据模板

- `COALA_Training_Template.md`
  - SFT / DPO 训练数据与项目推进模板

- `COALA_VectorStore_Instrumentation_Spec.md`
  - 向量存储埋点与记忆链路说明

## 如何阅读

如果你要：

- 启动程序：先看 `docs/ENTRYPOINTS.md`
- 跑测试：先看 `docs/TEST_MATRIX.md`
- 看部署：先看 `README.md`，再进入 `docs/IPC_FRP_QUICKSTART.md`
- 看工具生命周期：先看 `docs/TOOL_LIFECYCLE_ARCHITECTURE.md`
- 看最近改了什么：先看 `docs/UPDATE_LOG.md`
