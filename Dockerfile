# 使用轻量级的 Python 3.11 镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 1. 安装系统级依赖 (为了编译 llama.cpp)
# build-essential 和 cmake 是必须的
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

# 2. 复制依赖文件
COPY requirements.txt .

# 3. 关键步骤：编译最新版 llama-cpp-python
# 加上 -DGGML_NATIVE=OFF 是为了保证兼容性，防止在不同 CPU 上报错
# 我们强制升级，确保它包含最新的 Qwen 架构支持
RUN CMAKE_ARGS="-DGGML_NATIVE=OFF" pip install llama-cpp-python \
    --upgrade --force-reinstall --no-cache-dir \
    --verbose

# 4. 安装其他 Python 依赖
RUN pip install -r requirements.txt

# 5. 复制其余代码 (这一步其实会被 docker-compose 的挂载覆盖，但写上是个好习惯)
COPY . .

# 6. 设置环境变量，让 Python 输出不被缓存 (立刻看到打印日志)
ENV PYTHONUNBUFFERED=1

# 默认启动命令
CMD ["python", "main.py"]