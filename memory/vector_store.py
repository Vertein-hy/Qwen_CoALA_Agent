import os
import chromadb
from chromadb.utils import embedding_functions
from config.settings import VECTOR_DB_PATH
import uuid

class MemorySystem:
    def __init__(self):
        # 1. 初始化持久化存储
        # 这一步会在 data/chroma_db 文件夹下创建数据库文件
        print(f"正在初始化记忆库: {VECTOR_DB_PATH} ...")
        self.client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        
        # 2. 使用默认的轻量级 Embedding 模型 (all-MiniLM-L6-v2)
        # 它会自动下载一个小模型到本地，用来把文字变成向量
        self.emb_fn = embedding_functions.DefaultEmbeddingFunction()
        
        # 3. 获取或创建集合 (Collection)
        # 类似于 SQL 里的 Table
        self.collection = self.client.get_or_create_collection(
            name="evo_memories",
            embedding_function=self.emb_fn
        )
        print(f"记忆库加载完成。当前记忆条数: {self.collection.count()}")

    def add(self, text, metadata=None):
        """写入一条记忆"""
        if metadata is None:
            metadata = {"type": "conversation"}
            
        self.collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[str(uuid.uuid4())] # 自动生成唯一ID
        )

    def search(self, query, n_results=3):
        """检索相关记忆"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        
        # Chroma 返回的格式比较复杂，我们简化一下
        # results['documents'] 是一个列表的列表
        if not results['documents'][0]:
            return []
            
        return results['documents'][0] # 返回最相关的 n 条文本列表