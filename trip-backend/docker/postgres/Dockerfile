FROM postgres:16

# 安装 pgvector 向量检索扩展
RUN apt-get update && apt-get install -y \
    postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

# 初始化时自动启用扩展
COPY init-extensions.sql /docker-entrypoint-initdb.d/
