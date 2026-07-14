# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（sentence-transformers 需要）
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 安装依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 复制源码
COPY src/ ./src/

EXPOSE 8000

CMD ["uv", "run", "gunicorn", "src.main:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-w", "4", "--bind", "0.0.0.0:8000", \
     "--timeout", "120"]
