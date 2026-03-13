# 文档摘要工具

## 工具名

- `summarize_documents`

## 目标

在不打断主对话链路的前提下，让 Agent 能进入一个固定文件夹，读取其中的文档，并输出：

- 单文件摘要
- 整个目录的聚合摘要

这个工具是内置工具，不依赖技能内化流程，因此更适合作为稳定的货架能力。

## 当前支持的格式

### 直接支持

- 文本类
  - `.txt`
  - `.md`
  - `.rst`
  - `.py`
  - `.json`
  - `.yaml`
  - `.yml`
  - `.toml`
  - `.ini`
  - `.cfg`
  - `.csv`
  - `.tsv`
  - `.log`
  - `.xml`
  - `.html`
  - `.htm`

- Office Open XML
  - `.docx`
  - `.xlsx`
  - `.xlsm`
  - `.xltx`
  - `.xltm`

### PDF 支持

PDF 读取按这个顺序尝试：

1. `pypdf`
2. `PyPDF2`
3. 系统命令 `pdftotext`

如果三者都不可用，工具会返回警告，而不是报异常。

## 当前不直接支持

- `.doc`
- `.xls`

这两个是旧二进制格式，不适合在当前无额外依赖的条件下做稳定解析。

## 输入格式

### 1. 目录整体摘要

直接传目录路径：

```text
./docs
```

或空输入，默认当前工作目录：

```text

```

### 2. 单文件摘要

直接传文件路径：

```text
./docs/report.docx
```

### 3. 目录内指定文件

使用 `目录|相对文件路径`：

```text
./docs|report.docx
```

### 4. JSON 形式

适合后续更复杂的调用：

```json
{
  "path": "./docs",
  "scope": "file",
  "file_path": "report.docx",
  "max_files": 20
}
```

## 摘要模式

### `summarize_documents`

支持两种主要目录模式：

- `per_file`
  - 输出每个文件的独立摘要
  - 适合排查目录里具体都有什么

- `global`
  - 输出目录级总体摘要
  - 适合先快速看全局，不看逐文件明细

示例：

```json
{
  "path": "./docs",
  "scope": "global"
}
```

### `summarize_documents_semantic`

这是第二阶段工具。

它不会直接吞原始超长文档，而是基于第一阶段已经压缩好的文件摘要再做：

- 全局主题提取
- 优先文件排序
- 语义层面的总体总结

这一步的目的不是替代 LLM，而是先把目录级信息再压一层，降低后续进入小模型时的上下文压力。

## 输出形式

工具输出 Markdown。

### 单文件输出

- 根目录
- 文件路径
- 文件类型
- 推断标题
- 字符数
- 摘要
- 摘录

### 目录输出

- 根目录
- 汇总文件数量
- 文件类型统计
- 每个文件的独立摘要

### 全局输出

- 根目录
- 文件数量
- 文件类型统计
- 总体概览
- 重点文件

### 语义输出

- 根目录
- 分析文件数量
- 高权重主题词
- 语义概览
- 优先文件

## 架构位置

- 读取与摘要逻辑：
  - `modules/document_summary.py`
- ToolBox 注册与转发：
  - `modules/tools.py`
- builtin ToolSpec 暴露到发现链路：
  - `core/tool_lifecycle_runtime.py`

## 当前长文本策略

当前不是把整批原文直接送进小模型，而是先做两层压缩：

1. 第一层
   - 每个文件读取后生成：
     - `title`
     - `summary`
     - `excerpt`

2. 第二层
   - 对目录级多个文件摘要再聚合成：
     - `global`
     - `semantic`

这样做的目的很明确：
- 避免小模型直接吃超长原文
- 先把“读取”和“压缩”确定性完成
- 再决定是否需要后续语义推理

## 设计约束

- 这是确定性工具，不应依赖小模型现场编写 `python_repl` 去解析文档。
- 新格式支持优先加在 `modules/document_summary.py`，不要继续堆到 `modules/tools.py`。
- 工具只负责读取和摘要，不负责业务决策；何时调用仍由 Agent 路由层控制。
