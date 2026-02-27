import sys
# 这里不需要从 core.llm_interface 导入具体类类型检查，防止循环引用
# 如果需要类型提示，可以使用 TYPE_CHECKING
from typing import List

class EmotionEngine:
    def __init__(self, llm):
        self.llm = llm
        # 定义基本情绪
        self.valid_emotions = [
            "Happy (开心)", 
            "Sad (难过)", 
            "Angry (生气)", 
            "Curious (好奇)", 
            "Neutral (平静)", 
            "Excited (兴奋)"
        ]
        self.current_mood = "Curious (好奇)" # 默认初始状态

    def update_mood(self, user_input, recent_memories):
        """
        根据用户输入和当前记忆，推断新的情绪
        """
        # 构造简单的 Prompt 让模型判断情绪
        # 注意：为了速度，我们不进行复杂的 ReAct 思考，直接问
        
        prompt = f"""
[任务]
判断当前对话者的情绪反应。

[当前心情]
{self.current_mood}

[用户输入]
"{user_input}"

[选项]
{self.valid_emotions}

[要求]
只输出选项中的一个单词，不要解释。
"""
        
        try:
            # 临时构造 message
            messages = [{"role": "user", "content": prompt}]
            
            # 使用较低的 temperature 让判断稳定
            # 直接调用 llm.chat
            new_mood = self.llm.chat(messages, temperature=0.1).strip()
            
            # 简单的匹配逻辑
            for emotion in self.valid_emotions:
                # 只要模型输出包含关键词（比如 "Happy"），就更新
                if emotion.split(" ")[0].lower() in new_mood.lower():
                    self.current_mood = emotion
                    print(f"💓 心情更新: {self.current_mood}")
                    return self.current_mood
            
            return self.current_mood

        except Exception as e:
            # 如果出错（比如网络抖动），保持原心情，不要崩
            print(f"⚠️ 情感计算跳过: {e}")
            return self.current_mood