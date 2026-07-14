"""并发守卫模块。

限制并发 LLM 调用数量。
"""

import asyncio
from typing import Callable, Optional


class ConcurrencyGuard:
    """并发守卫。
    
    功能：
    - 全局并发限制
    - 单用户并发限制
    """
    
    def __init__(self, global_max: int = 10, per_user_max: int = 1):
        """初始化并发守卫。
        
        Args:
            global_max: 全局最大并发数
            per_user_max: 单用户最大并发数
        """
        self._global = asyncio.Semaphore(global_max)
        self._per_user: dict[int, asyncio.Semaphore] = {}
        self._per_user_max = per_user_max
        self._lock = asyncio.Lock()
    
    async def try_acquire(self, user_id: int) -> tuple[bool, Optional[Callable]]:
        """尝试获取信号量。
        
        Args:
            user_id: 用户 ID
            
        Returns:
            (成功标志, 释放函数)
        """
        # 全局检查
        if self._global.locked():
            return False, None
        
        # 单用户检查
        async with self._lock:
            if user_id not in self._per_user:
                self._per_user[user_id] = asyncio.Semaphore(self._per_user_max)
            
            user_sem = self._per_user[user_id]
            if user_sem.locked():
                return False, None
        
        # 获取信号量
        await self._global.acquire()
        
        async with self._lock:
            user_sem = self._per_user[user_id]
            await user_sem.acquire()
        
        released = False
        
        async def release() -> None:
            """释放信号量。"""
            nonlocal released
            if released:
                return
            released = True
            self._global.release()
            
            async with self._lock:
                if user_id in self._per_user:
                    self._per_user[user_id].release()
        
        return True, release
    
    async def __aenter__(self):
        """异步上下文管理器入口。"""
        await self._global.acquire()
        return self
    
    async def __aexit__(self, *args):
        """异步上下文管理器出口。"""
        self._global.release()


# 全局单例
concurrency_guard = ConcurrencyGuard()
