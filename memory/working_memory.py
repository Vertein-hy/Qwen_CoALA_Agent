class WorkingMemory:
    def __init__(self):
        # 存储对话历史，符合 OpenAI/Qwen 的 Chat 格式
        # e.g. [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        self.history = []
        self.current_mood = "Neutral"
    
    def add_message(self, role, content):
        """添加一条新的对话记录"""
        self.history.append({"role": role, "content": content})
        
    def get_context(self):
        """获取当前完整的上下文"""
        return self.history

    def update_mood(self, new_mood):
        self.current_mood = new_mood
        
    def clear(self):
        self.history = []