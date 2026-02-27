import sys
import os
import ollama

# ==========================================
# 🛡️ 局部网络防御盾
# 确保在这个模块里，代理绝对是被禁用的
# ==========================================
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    if k in os.environ:
        del os.environ[k]
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

# 引入配置
# 如果 config.settings 报错，就直接写死 "qwen3:1.7b"
try:
    from config.settings import OLLAMA_MODEL_NAME
except ImportError:
    OLLAMA_MODEL_NAME = "qwen3:1.7b" 

class LLMInterface:
    def __init__(self):
        self.model_name = OLLAMA_MODEL_NAME
        print(f"🔗 正在连接大脑 (模型: {self.model_name})...")
        
        # 【关键修改】显式创建 Client，强制使用 IPv4 地址
        # 这能绕过 localhost 的 DNS 解析问题和 VPN 劫持
        self.client = ollama.Client(host='http://127.0.0.1:11434')

        try:
            # 简单测试一下
            self.client.show(self.model_name)
            print("✅ 大脑连接正常！")
        except Exception as e:
            print(f"⚠️ 连接警告: {e}")
            print("尝试自动拉取模型...")
            try:
                self.client.pull(self.model_name)
            except:
                print("❌ 无法连接 Ollama，请检查后台服务是否运行。")
                # 不退出，防止整个程序崩溃，方便调试
                pass

    def chat(self, messages, temperature=0.7):
        """
        统一的聊天接口
        messages: [{"role": "user", "content": "..."}]
        """
        try:
            stream = self.client.chat(
                model=self.model_name,
                messages=messages,
                stream=True,
                options={
                    "temperature": temperature,
                    "num_ctx": 4096,
                    # === 关键修改：添加停止词 ===
                    # 一旦模型想输出 "Observation:"，强制停止
                    "stop": ["Observation:", "Observation"] 
                }
            )
            
            full_response = ""
            print("Evo: ", end="", flush=True)
            
            for chunk in stream:
                content = chunk['message']['content']
                print(content, end="", flush=True)
                full_response += content
            
            print() # 换行
            return full_response

        except Exception as e:
            error_msg = f"[Ollama Error]: {str(e)}"
            print(f"\n❌ {error_msg}")
            # 返回错误信息，不要让程序崩溃
            return "（大脑暂时短路了，请检查 Ollama 服务）"