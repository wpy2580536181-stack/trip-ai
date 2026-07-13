"""LLM 配置模块。

支持多 Provider 切换（DEEPSEEK / KIMI），主备自动切换。
对齐 Node.js 版本 loadLLMConfigForProvider / loadFallbackLLMConfig 模式。
"""

from __future__ import annotations

import logging
from typing import Optional

from langchain_openai import ChatOpenAI

from .settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider 注册表
# ---------------------------------------------------------------------------

# 所有已知 provider 名称（小写）
PROVIDERS = ("deepseek", "kimi", "agnese")


def _provider_config(provider: str) -> Optional[dict]:
    """从 settings 读取指定 provider 的连接配置。

    Args:
        provider: provider 名称（小写），如 "deepseek" / "kimi"

    Returns:
        {"api_key", "base_url", "model"} 字典；配置不完整时返回 None
    """
    p = provider.lower()
    if p == "deepseek":
        api_key = settings.deepseek_api_key
        base_url = settings.deepseek_base_url
        model = settings.deepseek_model
    elif p == "kimi":
        api_key = settings.kimi_api_key
        base_url = settings.kimi_base_url
        model = settings.kimi_model
    elif p == "agnese":
        api_key = settings.agnes_api_key
        base_url = settings.agnes_base_url
        model = settings.agnes_model
    else:
        logger.warning("未知的 LLM provider: %s", provider)
        return None

    if not api_key:
        return None

    return {"api_key": api_key, "base_url": base_url, "model": model}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_llm_config_for_provider(provider: str) -> Optional[dict]:
    """加载指定 provider 的配置（对齐 Node.js loadLLMConfigForProvider）。

    Returns:
        配置字典或 None（配置缺失时）
    """
    return _provider_config(provider)


def load_llm_config() -> dict:
    """加载主 provider 配置（对齐 Node.js loadLLMConfig）。

    优先使用 llm_primary_provider，回退到 model_provider。

    Raises:
        ValueError: 主 provider 配置不完整
    """
    primary = settings.llm_primary_provider or settings.model_provider.lower()
    cfg = _provider_config(primary)
    if not cfg:
        raise ValueError(
            f"主 LLM provider '{primary}' 配置不完整，请检查环境变量"
        )
    return cfg


def load_fallback_llm_config() -> Optional[dict]:
    """加载备用 provider 配置（对齐 Node.js loadFallbackLLMConfig）。

    Returns:
        备用配置字典；未配置或不可用时返回 None
    """
    fallback = settings.llm_fallback_provider
    if not fallback:
        return None
    cfg = _provider_config(fallback)
    if not cfg:
        logger.info("备用 LLM provider '%s' 未配置，禁用 fallback", fallback)
        return None
    return cfg


def create_llm(
    streaming: bool = True,
    temperature: float = 0.7,
    callbacks: Optional[list] = None,
) -> ChatOpenAI:
    """创建主 LLM 实例（向后兼容接口）。

    Args:
        streaming: 是否启用流式输出
        temperature: 温度参数
        callbacks: LangChain callback 列表（可选，默认注入 token_tracker）

    Returns:
        ChatOpenAI 实例
    """
    cfg = load_llm_config()
    return _build_chat_openai(cfg, streaming=streaming, temperature=temperature, callbacks=callbacks)


def create_llm_from_config(
    config: dict,
    streaming: bool = True,
    callbacks: Optional[list] = None,
) -> ChatOpenAI:
    """从配置字典创建 LLM 实例。

    Args:
        config: LLM 配置字典（需包含 model / api_key / base_url）
        streaming: 是否启用流式输出
        callbacks: LangChain callback 列表

    Returns:
        ChatOpenAI 实例
    """
    return _build_chat_openai(
        config,
        streaming=streaming,
        temperature=config.get("temperature", 0.7),
        callbacks=callbacks,
    )


def get_llm(provider: str = "default", streaming: bool = True, temperature: float = 0.7) -> ChatOpenAI:
    """获取指定 provider 的 LLM 实例。

    Args:
        provider: provider 名称；"default" 表示使用主 provider
        streaming: 是否流式
        temperature: 温度

    Returns:
        ChatOpenAI 实例

    Raises:
        ValueError: provider 配置缺失
    """
    if provider == "default":
        cfg = load_llm_config()
    else:
        cfg = load_llm_config_for_provider(provider)
        if not cfg:
            raise ValueError(f"LLM provider '{provider}' 配置不完整")
    return _build_chat_openai(cfg, streaming=streaming, temperature=temperature)


def get_fallback_llm(streaming: bool = True, temperature: float = 0.7) -> Optional[ChatOpenAI]:
    """获取备用 provider 的 LLM 实例。

    Returns:
        ChatOpenAI 实例；备用 provider 未配置时返回 None
    """
    cfg = load_fallback_llm_config()
    if not cfg:
        return None
    return _build_chat_openai(cfg, streaming=streaming, temperature=temperature)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_chat_openai(
    cfg: dict,
    streaming: bool = True,
    temperature: float = 0.7,
    callbacks: Optional[list] = None,
) -> ChatOpenAI:
    """统一构建 ChatOpenAI 实例。"""
    # 延迟导入避免循环依赖；仅在未显式传入 callbacks 时注入
    if callbacks is None:
        try:
            from src.services.agent.token_tracker import token_tracker
            callbacks = [token_tracker]
        except ImportError:
            callbacks = []

    return ChatOpenAI(
        model=cfg.get("model", settings.deepseek_model),
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        streaming=streaming,
        temperature=temperature,
        max_tokens=8000,
        callbacks=callbacks or None,
        # OpenAI 兼容 API：streaming 模式下请求 usage 字段
        # DeepSeek / Moonshot / OpenAI 全部支持 stream_options.include_usage
        model_kwargs=(
            {"stream_options": {"include_usage": True}} if streaming else {}
        ),
    )
