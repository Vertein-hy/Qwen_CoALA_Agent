# config/settings.py
import os

# Ollama 配置
# 如果你刚才用 Modelfile 创建了 "qwen3"，这里就填 "qwen3"
# 如果你没创建，只是 pull 了 "qwen2.5:1.5b"，这里就填 "qwen2.5:1.5b"
OLLAMA_MODEL_NAME = "qwen3:1.7b" 

# Ollama 服务地址 (默认是本地)
OLLAMA_HOST = "http://127.0.0.1:11434"

# 向量数据库路径 (保持不变)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTOR_DB_PATH = os.path.join(BASE_DIR, "data", "chroma_db")