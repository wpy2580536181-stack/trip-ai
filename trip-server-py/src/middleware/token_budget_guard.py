"""Token 预算守卫中间件。

将 services/agent/token_budget.py 的 TokenBudgetManager 包装为 FastAPI 依赖。
对齐 Node.js trip-server 的 createTokenBudgetGuard。
"""

import logging

from fastapi import Request, HTTPException

from src.services.agent.token_budget import token_budget_manager

logger = logging.getLogger(__name__)


async def token_budget_guard_dependency(request: Request) -> None:
    """Token 预算守卫依赖（FastAPI Depends）。

    双层检查：
    1. 用户级预算（每小时重置）
    2. 全局预算（每分钟重置）

    超预算时返回 429。

    用法::

        @router.post("/chat")
        async def chat(_: None = Depends(token_budget_guard_dependency)):
            ...
    """
    user = getattr(request.state, "user", None)
    user_id = getattr(user, "id", None) if user else None

    # 用户级检查
    user_budget = await token_budget_manager.check_user_budget(user_id or 0)
    if not user_budget["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={"code": 429, "error": "Token 额度已用尽，请稍后再试"},
        )

    # 全局检查
    global_budget = await token_budget_manager.check_global_budget()
    if not global_budget["allowed"]:
        raise HTTPException(
            status_code=503,
            detail={"code": 503, "error": "系统 Token 配额已满，请稍后再试"},
        )
