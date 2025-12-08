# ==============================
# 阶段 1: 最简 Dockerfile (单阶段)
# 目的: 确保 main_mcp.py 能够成功运行并识别 .env
# 修复: 移除 uv，直接使用 pip 确保依赖安装到系统路径。
# ------------------------------
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# 3. 复制应用程序文件和配置文件
COPY main_mcp.py .
COPY .env .

# 运行命令: 使用系统保证存在的 'python' 解释器
CMD ["python", "main_mcp.py"]