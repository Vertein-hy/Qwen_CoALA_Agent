import os
import sys
import subprocess
import time

def install_cpu_llama():
    print("=== 正在准备安装免编译版 llama-cpp-python (CPU) ===")
    
    # 1. 强制清理环境变量
    # 之前报错是因为环境变量里可能有 CMAKE_ARGS，导致 pip 试图去编译
    # 我们把它们临时删掉，强制 pip 只找预编译包
    if "CMAKE_ARGS" in os.environ:
        del os.environ["CMAKE_ARGS"]
    if "FORCE_CMAKE" in os.environ:
        del os.environ["FORCE_CMAKE"]
    
    python_exe = sys.executable

    # 2. 卸载冲突库
    print("\n[1/3] 清理旧环境...")
    subprocess.run([python_exe, "-m", "pip", "uninstall", "-y", "llama-cpp-python", "ollama"], check=False)

    # 3. 安装预编译 Wheel (关键步骤)
    # --extra-index-url 指向 abetlen 的官方预编译仓库
    # cpu/ 目录下存放着 windows 的 .whl 文件
    # --upgrade 确保拿最新版 (支持 Qwen3)
    print("\n[2/3] 下载并安装预编译包 (这可能需要几分钟)...")
    
    cmd = [
        python_exe, "-m", "pip", "install", 
        "llama-cpp-python",
        "--upgrade",
        "--force-reinstall",
        "--no-cache-dir",
        "--extra-index-url", "https://abetlen.github.io/llama-cpp-python/whl/cpu"
    ]
    
    try:
        result = subprocess.run(cmd, check=True)
        if result.returncode == 0:
            print("\n[3/3] ✅ 安装成功！")
            verify_installation()
        else:
            print("\n❌ 安装失败，pip 返回错误。")
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 安装过程出错: {e}")
        print("建议：请以管理员身份运行终端重试。")

def verify_installation():
    """验证是否能加载 Qwen3"""
    print("\n=== 验证安装 ===")
    try:
        import llama_cpp
        print(f"llama_cpp 版本: {llama_cpp.__version__}")
        print("依赖库加载正常。现在你可以切换回 GGUF 模式了。")
    except ImportError:
        print("❌ 依然无法导入 llama_cpp，请检查 Python 环境。")

if __name__ == "__main__":
    install_cpu_llama()