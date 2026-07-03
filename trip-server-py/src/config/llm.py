"""LLM 配置模块。

创建 ChatOpenAI 实例和备用 LLM 配置。
"""

from langchain_openai import ChatOpenAI
from typing import Optional, Any
from .settings import settings


def create_llm(streaming: bool = True) -> ChatOpenAI:
    """创建主 LLM 实例。
    
    Args:
        streaming: 是否启用流式输出
        
    Returns:
        ChatOpenAI 实例
    """
    return ChatOpenAI(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        streaming=streaming,
        temperature=0.7,
    )


def create_llm_from_config(config: dict, streaming: bool = True) -> ChatOpenAI:
    """从配置字典创建 LLM 实例。
    
    Args:
        config: LLM 配置字典
        streaming: 是否启用流式输出
        
    Returns:
        ChatOpenAI 实例
    """
    return ChatOpenAI(
        model=config.get("model", settings.deepseek_model),
        api_key=config.get("api_key", settings.deepseek_api_key),
        base_url=config.get("base_url", settings.deepseek_base_url),
        streaming=streaming,
        temperature=config.get("temperature", 0.7),
    )


def load_fallback_llm_config() -> Optional[dict]:
    """加载备用 LLM 配置。
    
    Returns:
        备用 LLM 配置字典，如果未配置则返回 None
    """
    # 检查是否有备用 LLM 配置
    fallback_model = getattr(settings, "deepseek_fallback_model", None)
    if not fallback_model:
        return None
    
    return {
        "model": fallback_model,
        "api_key": getattr(settings, "deepseek_fallback_api_key", settings.deepseek_api_key),
        "base_url": getattr(settings, "deepseek_fallback_base_url", settings.deepseek_base_url),
        "temperature": 0.7,
    }
