"""pydantic-settings 统一配置（合并所有 env 读取）"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置（从 .env 文件 + 环境变量读取）"""
    
    model_config = {"env_file": ".env", "extra": "ignore"}
    
    # 数据库配置
    database_url: str = "mysql://root:root@localhost:3306/trip_db"
    
    # JWT 配置
    jwt_secret: str = "change-this-to-a-random-secret-string"
    jwt_algorithm: str = "HS256"
    jwt_expires_in_days: int = 7
    
    # 服务配置
    port: int = 8000  # 开发期用 8000，避免与 Node.js 3000 冲突
    cors_demo: bool = True
    cors_origin: Optional[str] = None
    
    # 大模型配置
    model_provider: str = "DEEPSEEK"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    
    # 环境配置
    node_env: str = "development"
    
    # Chroma 向量数据库
    chroma_url: str = "http://localhost:8001"  # 注意：Chroma 容器映射 8001:8000
    
    # HuggingFace 模型下载镜像
    hf_endpoint: str = "https://hf-mirror.com/"
    
    # 高德 MCP
    amap_maps_api_key: str = ""
    unsplash_access_key: str = ""
    
    # Redis 配置
    redis_url: str = "redis://localhost:6379"
    
    # Token 预算配置
    token_budget_user: int = 50000  # 单用户每小时预算
    token_budget_global: int = 200000  # 全局每分钟预算
    
    # 并发守卫配置
    concurrency_global: int = 10  # 全局并发限制
    concurrency_user: int = 1  # 单用户并发限制


settings = Settings()
