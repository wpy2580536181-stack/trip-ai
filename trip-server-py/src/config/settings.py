"""pydantic-settings 统一配置（合并所有 env 读取）"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置（从 .env 文件 + 环境变量读取）"""
    
    model_config = {"env_file": ".env", "extra": "ignore"}
    
    # 数据库配置
    database_url: str = "mysql+aiomysql://root:root@localhost:3306/trip_db"
    
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
    
    # KIMI / Moonshot Provider 配置（可选）
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "moonshot-v1-8k"
    
    # Provider 切换配置
    llm_primary_provider: str = "deepseek"
    llm_fallback_provider: str = "kimi"
    
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
    
    # LLM 缓存配置
    llm_cache_enabled: bool = False  # LLM 响应缓存开关（默认关闭，调试期避免脏缓存）
    llm_cache_ttl_s: int = 600  # LLM 缓存 TTL（秒）
    llm_cache_max_size: int = 200  # 内存模式最大条目数
    
    # Tool 缓存配置
    tool_cache_enabled: bool = True  # 工具结果缓存开关
    tool_cache_backend: str = "auto"  # auto / redis / memory
    
    # 告警系统配置
    alert_enabled: bool = False  # 是否启用告警调度
    alert_webhook_url: str = ""  # Webhook URL
    alert_webhook_type: str = "feishu"  # feishu / dingtalk / slack / wecom / custom
    alert_threshold: float = 0.5  # 满意率阈值（0-1）
    alert_min_feedbacks: int = 5  # 最小反馈数（防误报）
    alert_interval_seconds: int = 300  # 检测间隔（秒），默认 5 分钟
    alert_cooldown_seconds: int = 3600  # 去重冷却期（秒），默认 1 小时
    alert_window_minutes: int = 60  # 查询窗口（分钟）
    dashboard_url: str = "http://localhost:5173"  # Dashboard URL

    # 速率限制配置（可通过环境变量覆盖，用于压测时临时调高）
    rate_limit_auth_max: int = 10           # 认证接口限流（次/窗口）
    rate_limit_auth_window: int = 900       # 认证限流窗口（秒），默认 15 分钟
    rate_limit_global_max: int = 2000       # 全局限流（次/分钟）
    rate_limit_chat_max: int = 200          # Chat 限流（次/分钟）
    rate_limit_recommend_max: int = 50      # Recommend 限流（次/分钟）
    rate_limit_optimize_max: int = 50       # Optimize 限流（次/分钟）
    rate_limit_feedback_max: int = 30       # 反馈限流（次/小时）
    rate_limit_knowledge_max: int = 100     # 知识库限流（次/分钟）


settings = Settings()
