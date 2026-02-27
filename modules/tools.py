import sys
import io
import contextlib
import os
import importlib.util

class ToolBox:
    def __init__(self):
        self.tools = {
            "python_repl": self.python_repl,
            "write_file": self.write_file,
            "read_file": self.read_file
        }
        self.python_state = {} 
        self.load_internalized_skills()
    
    def load_internalized_skills(self):
        skill_path = os.path.join("skills", "internalized", "custom_skills.py")
        if not os.path.exists(skill_path):
            return

        try:
            if "custom_skills" in sys.modules:
                del sys.modules["custom_skills"]
            
            spec = importlib.util.spec_from_file_location("custom_skills", skill_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if callable(attr) and not attr_name.startswith("_"):
                    self.tools[attr_name] = attr
        except Exception as e:
            print(f"⚠️ 技能加载失败: {e}")

    def get_tool_desc(self):
        desc = "【基础工具】\n"
        desc += "1. python_repl: 执行 Python 代码。\n"
        desc += "2. write_file: 写入文件 (文件名|内容)。\n"
        desc += "   * 如果内容是动态生成的(如函数结果)，请直接传入Python代码，系统会自动处理。\n"
        desc += "3. read_file: 读取文件 (文件名)。\n"
        
        skill_desc = ""
        for name, func in self.tools.items():
            if name not in ["python_repl", "write_file", "read_file"]:
                import inspect
                try:
                    sig = str(inspect.signature(func))
                except:
                    sig = "()"
                doc = func.__doc__.strip() if func.__doc__ else "无说明"
                skill_desc += f"        *. {name}{sig}: [已预加载] {doc}\n"
        
        if skill_desc:
            desc += "\n【🌟 专属技能 (可以直接 Action 调用)】\n" + skill_desc
            
        return desc

    def execute(self, tool_name, tool_input):
        if tool_name not in self.tools:
            return f"错误: 找不到工具 '{tool_name}'"
        
        try:
            print(f"🔨 执行工具: {tool_name} ...")
            
            # 智能转发内化技能
            if tool_name not in ["python_repl", "write_file", "read_file"]:
                if tool_input:
                    code_to_run = f"print({tool_name}({tool_input}))"
                else:
                    code_to_run = f"print({tool_name}())"
                print(f"🔄 转发至引擎: {code_to_run}")
                return self.python_repl(code_to_run)
            
            return self.tools[tool_name](tool_input)
        except Exception as e:
            return f"执行出错: {e}"

    def python_repl(self, code):
        code = code.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[-1]
        if code.endswith("```"):
            code = code.rsplit("\n", 1)[0]
        code = code.strip()
        
        output_buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(output_buffer):
                # === 关键修改 ===
                # 使用 self.python_state 作为全局作用域
                # 这样 Step 1 定义的变量，Step 2 依然可以用
                exec(code, self.python_state)
                
            res = output_buffer.getvalue().strip()
            return res if res else "执行成功，无输出 (变量已保存到内存)。"
        except Exception as e:
            return f"Python Error: {e}"

    def write_file(self, args):
        # === 核心修复逻辑 ===
        # 尝试按照 "文件名|内容" 格式解析
        try:
            if "|" in args:
                name, content = args.split("|", 1)
                # 进一步检查：如果 content 看起来像 Python 代码，说明模型可能用错了
                # 但如果用户就是想写代码到文件里呢？这是一个权衡。
                # 这里的策略是：只有当 split 失败时，才尝试当做代码运行。
                
                path = os.path.join("data", name.strip())
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"文件 {path} 写入成功"
            else:
                raise ValueError("没有找到分隔符 |")
                
        except ValueError:
            # 如果解析失败，检查是否是 Python 代码
            # 模型可能会把代码直接传进来，比如 with open(...)
            if "open(" in args or "write(" in args or "def " in args:
                print("🔄 检测到 Python 代码格式，转发至 python_repl 执行...")
                return self.python_repl(args)
            
            return "错误: 输入格式应为 '文件名|内容'，或者是一段有效的 Python 文件操作代码。"

    def read_file(self, name):
        path = os.path.join("data", name.strip())
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return "文件不存在"