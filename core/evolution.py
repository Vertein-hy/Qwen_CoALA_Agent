import os
import re
from core.llm_interface import LLMInterface

class SkillEvolver:
    def __init__(self, llm: LLMInterface):
        self.llm = llm
        # 确保目录存在
        self.skill_dir = os.path.join("skills", "internalized")
        if not os.path.exists(self.skill_dir):
            os.makedirs(self.skill_dir)
            
        self.skill_file = os.path.join(self.skill_dir, "custom_skills.py")
        
        # 初始化文件头
        if not os.path.exists(self.skill_file):
            with open(self.skill_file, "w", encoding="utf-8") as f:
                f.write("# Auto-generated skills by Neko\n# 这个文件存放 Neko 学会的新技能\n\n")

    def evolve(self, user_intent, successful_code):
        print(f"🧬 [进化启动] 正在评估代码价值...")
        
        # 1. 让 LLM 提取/生成函数
        prompt = f"""
[任务]
将以下 Python 代码封装成函数。
[用户意图]
{user_intent}
[原始代码]
{successful_code}
[要求]
1. 仅输出函数代码。
2. 函数名 snake_case。
3. 尽量通用化参数 (如把 10 改为 n)。
"""
        try:
            function_code = self.llm.chat([{"role": "user", "content": prompt}], temperature=0.1)
            function_code = function_code.replace("```python", "").replace("```", "").strip()
            
            if "def " not in function_code:
                print("❌ 代码不合法，跳过。")
                return

            # === 🛡️ 新增：防重复检查 ===
            # 提取函数名
            func_name_match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", function_code)
            if func_name_match:
                func_name = func_name_match.group(1)
                
                # 读取现有文件内容
                with open(self.skill_file, "r", encoding="utf-8") as f:
                    existing_content = f.read()
                
                # 如果函数名已存在，就放弃写入
                if f"def {func_name}(" in existing_content:
                    print(f"⚠️ 技能 [{func_name}] 已存在，跳过进化 (避免重复)。")
                    return
            # ============================

            # 写入文件
            with open(self.skill_file, "a", encoding="utf-8") as f:
                f.write(f"\n\n# Source: {user_intent}\n")
                f.write(function_code + "\n")
            
            print(f"✨ 新技能 [{func_name}] 已习得并保存！")
            
        except Exception as e:
            print(f"❌ 进化出错: {e}")