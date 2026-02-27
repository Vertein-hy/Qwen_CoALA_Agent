import sys
import yaml
import re
import os
from pathlib import Path
from core.llm_interface import LLMInterface
from memory.working_memory import WorkingMemory
from memory.vector_store import MemorySystem
from modules.tools import ToolBox
from modules.emotion import EmotionEngine
from core.evolution import SkillEvolver

class CognitiveAgent:
    def __init__(self):
        # 1. 基础组件初始化
        self.prompts = self._load_prompts()
        self.working_memory = WorkingMemory()
        self.llm = LLMInterface()
        self.tools = ToolBox()
        
        # 2. 高级模块初始化
        self.emotion_engine = EmotionEngine(self.llm)
        self.evolver = SkillEvolver(self.llm)
        
        # 3. 记忆系统 (允许失败)
        try:
            self.long_term_memory = MemorySystem()
        except Exception as e:
            print(f"⚠️ 记忆系统初始化失败: {e}")
            self.long_term_memory = None
        
        self._init_system_prompt()

    def _load_prompts(self):
        prompt_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
        with open(prompt_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _init_system_prompt(self):
        # 初始心情
        initial_mood = self.emotion_engine.current_mood
        
        # 构造 ReAct 风格的 System Prompt
        self.base_system_prompt = f"""
你是一个名为 "Neko" 的智能代理 (基于 Qwen3)。
你的创造者是 HY。

[性格]
你是一只猫娘/猫耳少年，说话活泼可爱。
当前心情: {{mood}}

[可用工具]
{self.tools.get_tool_desc()}

[思考格式]
User: (问题)
Thought: (思考)
Action: (工具名)
Action Input: (代码或参数)
Observation: (运行结果)
...
Final Answer: (最终回答)

[注意]
- 遇到计算或文件操作，必须用 python_repl。
- 只有在这一轮对话结束时，才输出 Final Answer。
"""
        # 初始填充
        self.update_system_prompt(initial_mood, "[暂无记忆]")

    def update_system_prompt(self, mood, memories):
        """动态更新 System Prompt"""
        content = self.base_system_prompt.format(mood=mood)
        content += f"\n[相关记忆]\n{memories}"
        
        if self.working_memory.history:
            self.working_memory.history[0]['content'] = content
        else:
            self.working_memory.add_message("system", content)

    def run(self, user_input):
        print(f"\n👂 User: {user_input}")
        
        # 1. 检索与感知
        related_memories = []
        if self.long_term_memory:
            related_memories = self.long_term_memory.search(user_input, n_results=2)
            if related_memories:
                print(f"🧠 回忆: {related_memories}")
        
        # 2. 情感计算
        current_mood = self.emotion_engine.update_mood(user_input, related_memories)
        
        # 3. 更新 Context
        memory_str = "\n".join([f"- {m}" for m in related_memories]) if related_memories else "[暂无]"
        self.update_system_prompt(current_mood, memory_str)
        self.working_memory.add_message("user", user_input)
        
        # 4. ReAct 循环
        max_steps = 5
        current_step = 0
        
        # 初始化 messages 用于本轮推理 (包含历史 context)
        messages = self.working_memory.get_context()
        
        while current_step < max_steps:
            current_step += 1
            print(f"⏳ Step {current_step}...")
            
            # LLM 生成
            response = self.llm.chat(messages)
            
            # 解析 Action
            action_match = re.search(r"Action:\s*(.*?)(?:\n|$)", response)
            input_match = re.search(r"Action Input:\s*([\s\S]*?)(?:\nObservation:|$)", response)
            
            # --- 情况 A: 使用工具 ---
            if action_match and input_match:
                tool_name = action_match.group(1).strip()
                tool_input = input_match.group(1).strip()
                if "Observation:" in tool_input: 
                    tool_input = tool_input.split("Observation:")[0].strip()
                
                print(f"🔧 工具: {tool_name} | 输入: {tool_input[:30]}...")
                
                observation = self.tools.execute(tool_name, tool_input)
                print(f"👀 结果: {observation}")
                
                # 追加历史，让模型看到结果
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
                continue
            
            # --- 情况 B: 最终回答 ---
            if "Final Answer:" in response:
                final_ans = response.split("Final Answer:")[-1].strip()
                print(f"✅ Neko: {final_ans}")
                
                # 【修复点】这里正确传入了 user_input
                self._try_evolve(messages, user_input)
                
                # 存入记忆
                if self.long_term_memory:
                    self.long_term_memory.add(f"User: {user_input} | Neko: {final_ans}")
                
                # 更新短期记忆
                self.working_memory.add_message("assistant", final_ans)
                return final_ans
            
            # --- 情况 C: 直接回答 (Fallback) ---
            print(f"✅ Neko: {response}")
            self.working_memory.add_message("assistant", response)
            return response

        return "呜呜，任务太难了，我处理不过来..."

    def _try_evolve(self, messages, user_input):
            valid_code = None
            for msg in reversed(messages):
                if msg['role'] == 'assistant' and "Action: python_repl" in msg['content']:
                    content = msg['content']
                    code_match = re.search(r"Action Input:\s*([\s\S]*?)(?:\n|$)", content)
                    if code_match:
                        code = code_match.group(1).strip()
                        if "Observation:" in code: code = code.split("Observation:")[0].strip()
                        
                        # === 关键修改：过滤掉只是调用函数的代码 ===
                        # 如果代码里只有一行，且包含括号，大概率是调用，不值得存
                        if len(code.split('\n')) <= 2 and "(" in code and ")" in code:
                            print("💤 仅检测到函数调用，跳过进化。")
                            return

                        # 只有包含复杂逻辑（比如 def, for, while）才进化
                        if any(kw in code for kw in ["def ", "for ", "while ", "import "]):
                            if len(code) > 15:
                                valid_code = code
                                break
            
            if valid_code:
                self.evolver.evolve(user_input, valid_code)