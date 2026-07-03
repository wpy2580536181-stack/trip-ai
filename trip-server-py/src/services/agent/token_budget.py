"""Token 预算管理模块。

限制每次对话的 token 消耗量。
"""

import time
import asyncio
from typing import Optional


class TokenBudgetManager:
    """Token 预算管理器。
    
    功能：
    - 用户级预算（每小时重置）
    - 全局预算（每分钟重置）
    - 记录用量
    """
    
    def __init__(
        self,
        user_token_limit: int = 50_000,
        global_token_limit: int = 200_000,
        user_window: int = 3600,  # 1 hour
        global_window: int = 60,  # 1 minute
    ):
        """初始化 Token 预算管理。
        
        Args:
            user_token_limit: 用户 token 限制（每小时）
            global_token_limit: 全局 token 限制（每分钟）
            user_window: 用户窗口时间（秒）
            global_window: 全局窗口时间（秒）
        """
        self.user_limit = user_token_limit
        self.global_limit = global_token_limit
        self.user_window = user_window
        self.global_window = global_window
        
        # 用户数据：{user_id: {"total": N, "reset_at": timestamp}}
        self._user_data: dict[int, dict] = {}
        
        # 全局数据
        self._global_data = {"total": 0, "reset_at": 0}
        
        # 锁
        self._lock = asyncio.Lock()
    
    async def check_user_budget(self, user_id: int) -> dict:
        """检查用户预算。
        
        Args:
            user_id: 用户 ID
            
        Returns:
            包含 allowed, current, limit 的字典
        """
        async with self._lock:
            now = time.time()
            entry = self._user_data.get(user_id)
            
            if not entry or now >= entry["reset_at"]:
                # 重置
                return {
                    "allowed": True,
                    "current": 0,
                    "limit": self.user_limit,
                }
            
            return {
                "allowed": entry["total"] < self.user_limit,
                "current": entry["total"],
                "limit": self.user_limit,
            }
    
    async def check_global_budget(self) -> dict:
        """检查全局预算。
        
        Returns:
            包含 allowed, current, limit 的字典
        """
        async with self._lock:
            now = time.time()
            
            if now >= self._global_data["reset_at"]:
                # 重置
                return {
                    "allowed": True,
                    "current": 0,
                    "limit": self.global_limit,
                }
            
            return {
                "allowed": self._global_data["total"] < self.global_limit,
                "current": self._global_data["total"],
                "limit": self.global_limit,
            }
    
    async def record_user_usage(self, user_id: int, tokens: int) -> None:
        """记录用户 token 使用量。
        
        Args:
            user_id: 用户 ID
            tokens: 消耗的 token 数
        """
        async with self._lock:
            now = time.time()
            entry = self._user_data.get(user_id)
            
            if not entry or now >= entry["reset_at"]:
                # 新窗口
                self._user_data[user_id] = {
                    "total": tokens,
                    "reset_at": now + self.user_window,
                }
            else:
                # 累计
                entry["total"] += tokens
    
    async def record_global_usage(self, tokens: int) -> None:
        """记录全局 token 使用量。
        
        Args:
            tokens: 消耗的 token 数
        """
        async with self._lock:
            now = time.time()
            
            if now >= self._global_data["reset_at"]:
                # 新窗口
                self._global_data = {
                    "total": tokens,
                    "reset_at": now + self.global_window,
                }
            else:
                # 累计
                self._global_data["total"] += tokens
    
    async def get_user_stats(self, user_id: int) -> Optional[dict]:
        """获取用户统计信息。
        
        Args:
            user_id: 用户 ID
            
        Returns:
            统计信息字典，如果用户不存在则返回 None
        """
        async with self._lock:
            entry = self._user_data.get(user_id)
            if not entry:
                return None
            
            return {
                "total": entry["total"],
                "remaining": max(0, self.user_limit - entry["total"]),
                "limit": self.user_limit,
                "reset_in": max(0, int(entry["reset_at"] - time.time())),
            }
    
    async def get_global_stats(self) -> dict:
        """获取全局统计信息。
        
        Returns:
            统计信息字典
        """
        async with self._lock:
            now = time.time()
            
            return {
                "total": self._global_data["total"],
                "remaining": max(0, self.global_limit - self._global_data["total"]),
                "limit": self.global_limit,
                "reset_in": max(0, int(self._global_data["reset_at"] - now)),
            }


# 全局单例
token_budget_manager = TokenBudgetManager()
