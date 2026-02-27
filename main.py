import sys
import colorama
from colorama import Fore, Style
from core.agent import CognitiveAgent
import os
# --- 新增这两行 ---
# 强制忽略系统代理，直接连接本地
os.environ["NO_PROXY"] = "localhost,127.0.0.1"
os.environ["no_proxy"] = "localhost,127.0.0.1"
# -----------------

# 初始化颜色
colorama.init(autoreset=True)

def main():
    print(Fore.CYAN + "=== Qwen CoALA Agent (Ollama Mode) ===")
    print(Fore.YELLOW + "初始化中...")

    # --- 移除旧的文件检查逻辑 ---
    # Ollama 不需要检查 .gguf 文件路径，因为它由服务管理
    
    try:
        # 启动 Agent
        # agent 内部会去连接 Ollama，如果连不上会报错并退出
        agent = CognitiveAgent()
        
    except Exception as e:
        print(Fore.RED + f"\n[致命错误] 启动失败: {e}")
        print(Fore.YELLOW + "提示: 请确保已安装并运行 Ollama (在终端输入 'ollama list' 测试)")
        return

    print(Fore.GREEN + "\n✅ Neko 已就绪! (输入 'exit' 退出)\n")

    # 对话循环
    while True:
        try:
            # 获取用户输入
            user_input = input(Fore.BLUE + "User: " + Style.RESET_ALL)
            
            # 退出指令
            if user_input.lower() in ["exit", "quit"]:
                print("Bye!")
                break
            
            # 空输入处理
            if not user_input.strip():
                continue
                
            # 运行 Agent 循环
            agent.run(user_input)
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(Fore.RED + f"运行出错: {e}")

if __name__ == "__main__":
    main()