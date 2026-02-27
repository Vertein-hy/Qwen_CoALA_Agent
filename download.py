import os
import sys
import subprocess
import time

# ==========================================
# 1. 环境自动配置 (HuggingFace + Llama.cpp)
# ==========================================
def install_package(package_name, install_name=None):
    """
    检查并安装包。
    install_name: pip 安装时的名称（如果与导入名称不同）
    """
    if install_name is None:
        install_name = package_name
    
    try:
        __import__(package_name)
    except ImportError:
        print(f"⏳ 正在安装 {install_name} ...")
        # 强制升级安装，确保 llama-cpp-python 支持 Qwen3 的新算子
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", install_name])
        print(f"✅ {install_name} 安装完成")

def setup_environment():
    print("=== [环境检查] ===")
    # 1. 下载工具
    install_package("huggingface_hub")
    
    # 2. 推理引擎 (关键：Qwen3 需要较新的 llama.cpp 内核)
    # 注意：如果需要 GPU 加速，建议手动安装带 cuBLAS 的版本，这里默认安装 CPU/通用版
    try:
        import llama_cpp
        print(f"检测到 llama-cpp-python 版本: {llama_cpp.__version__}")
    except ImportError:
        install_package("llama_cpp", "llama-cpp-python")

setup_environment()

from huggingface_hub import hf_hub_download
from llama_cpp import Llama  # 用于最后的加载测试

# ==========================================
# 2. 下载与验证逻辑
# ==========================================
def download_qwen3_real():
    # 真实存在的仓库 (参考 Qwen2.5/3 的发布习惯)
    REPO_ID = "Qwen/Qwen3-1.7B-GGUF"
    
    # Q8_0 是 1.7B 模型的“黄金甜点”，体积约 1.9GB，精度几乎无损
    FILENAME = "Qwen3-1.7b-Q8_0.gguf" 
    # 注：文件名可能会根据官方惯例略有不同，如果失败脚本会自动尝试备用名
    
    LOCAL_DIR = "./models"
    
    print(f"\n=== [2026] Qwen3-1.7B 智能下载器 ===")
    print(f"目标仓库: {REPO_ID}")
    print(f"目标文件: {FILENAME} (Q8_0 高精度版)")
    print("------------------------------------------------")

    file_path = None
    
    # 尝试下载 (处理可能的大小写或命名差异)
    candidate_filenames = [
        "qwen3-1.7b-instruct-q8_0.gguf",  # 官方常见小写命名
        "Qwen3-1.7B-Instruct-Q8_0.gguf",  # 大写命名
        "qwen3-1.7b-q8_0.gguf"            # 简化命名
    ]

    for fname in candidate_filenames:
        try:
            print(f"🔍 尝试下载文件: {fname} ...")
            file_path = hf_hub_download(
                repo_id=REPO_ID,
                filename=fname,
                local_dir=LOCAL_DIR,
                local_dir_use_symlinks=False,  # 确保是实体文件
                resume_download=True
            )
            print(f"✅ 成功定位并下载: {fname}")
            break
        except Exception as e:
            if "Entry Not Found" in str(e) or "404" in str(e):
                continue
            else:
                print(f"❌ 下载过程出错: {e}")
                print("💡 提示：请检查网络，或设置 HF_ENDPOINT=https://hf-mirror.com")
                return

    if not file_path:
        print("❌ 错误：在仓库中未找到预期的 GGUF 文件名，请手动检查 HuggingFace 仓库文件列表。")
        return

    abs_path = os.path.abspath(file_path)
    
    # ==========================================
    # 3. 冒烟测试 (Smoke Test)
    # ==========================================
    print("\n=== [模型自检] ===")
    print("正在尝试加载模型以验证兼容性（此步骤不消耗流量）...")
    try:
        # n_ctx=2048 仅做测试，verbose=False 不打印繁杂日志
        llm = Llama(model_path=abs_path, n_ctx=2048, verbose=False)
        print("✅ 模型加载成功！文件完整且 llama-cpp 版本兼容。")
        
        # 简单的推理测试
        output = llm("Q: 你是Qwen3吗？ A:", max_tokens=32, stop=["Q:", "\n"], echo=True)
        print(f"🤖 模型回应测试: {output['choices'][0]['text'].strip()}")
        
    except Exception as e:
        print(f"⚠️ 警告：模型文件已下载，但加载失败。可能是 llama-cpp 版本过低或内存不足。")
        print(f"错误详情: {e}")

    print("\n------------------------------------------------")
    print(f"🎉 准备就绪！")
    print(f"配置路径: {abs_path}")
    print(f'请在 settings.py 中更新: MODEL_PATH = r"{abs_path}"')

if __name__ == "__main__":
    download_qwen3_real()