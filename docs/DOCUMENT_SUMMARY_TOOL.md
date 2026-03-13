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

## 架构位置

- 读取与摘要逻辑：
  - `modules/document_summary.py`
- ToolBox 注册与转发：
  - `modules/tools.py`
- builtin ToolSpec 暴露到发现链路：
  - `core/tool_lifecycle_runtime.py`

## 设计约束

- 这是确定性工具，不应依赖小模型现场编写 `python_repl` 去解析文档。
- 新格式支持优先加在 `modules/document_summary.py`，不要继续堆到 `modules/tools.py`。
- 工具只负责读取和摘要，不负责业务决策；何时调用仍由 Agent 路由层控制。
