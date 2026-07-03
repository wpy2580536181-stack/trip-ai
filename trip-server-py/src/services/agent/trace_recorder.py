"""Trace Recorder 模块。

记录 Agent 执行轨迹到 agent_steps 表。
迁移自 Node.js 版本的 traceRecorder.ts。
"""

import time
from typing import Optional, Any

from src.config.database import async_session
from src.models.agent_step import AgentStep


class TraceRecorder:
    """Agent Step Trace Recorder。
    
    把 agent 决策过程（tool 调用、step 耗时）落 DB，
    方便 admin 回放。
    
    设计：
    - buffer 模式：每个 step add 到内存（避免 N+1 DB 写入）
    - flush 模式：agent 完成后一次 createMany
    - 失败只 warn，不影响 agent 业务
    - 同一 message Id 的 step 顺序由调用方保证
    """
    
    def __init__(self, message_id: int):
        """初始化 TraceRecorder。
        
        Args:
            message_id: 消息 ID（agent_steps 表 FK）
        """
        self.message_id = message_id
        self.steps: list[dict] = []
        self._parent_step_map: dict[int, int] = {}
    
    def add(self, step: dict) -> None:
        """添加一条 step 记录到内存 buffer。
        
        Args:
            step: Step 数据字典，包含：
                - step: 步骤编号
                - type: 步骤类型（tool_start/tool_end/chunk/complete/error）
                - name: 工具或节点名称（可选）
                - args: 工具调用参数（可选）
                - output: 输出内容（可选）
                - duration_ms: 耗时毫秒数（可选）
                - error: 错误信息（可选）
        """
        self.steps.append(step)
    
    async def flush(self) -> None:
        """写入 DB。
        
        失败只 warn，不抛错。
        """
        if not self.steps:
            return
        
        try:
            # 构建批量插入数据
            data = []
            for s in self.steps:
                data.append({
                    "message_id": self.message_id,
                    "step": s.get("step", 0),
                    "type": s.get("type", "unknown"),
                    "name": s.get("name"),
                    "args": s.get("args"),
                    "output": s.get("output"),
                    "duration_ms": s.get("duration_ms"),
                    "error": s.get("error"),
                })
            
            # 批量插入
            async with async_session() as session:
                session.add_all([AgentStep(**d) for d in data])
                await session.commit()
        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"agent trace 落 DB 失败: {e}",
                extra={"message_id": self.message_id, "count": len(self.steps)},
            )
    
    def get_steps(self) -> list[dict]:
        """获取当前已 buffer 的 steps（测试用）。"""
        return list(self.steps)
    
    def set_parent_step(self, step_number: int, parent_step_number: int) -> None:
        """设置 step 的父步骤关系。"""
        self._parent_step_map[step_number] = parent_step_number
    
    def get_parent_step(self, step_number: int) -> Optional[int]:
        """获取某 step 的父步骤。"""
        return self._parent_step_map.get(step_number)
    
    def clear_parent_step_map(self) -> None:
        """清空父步骤映射。"""
        self._parent_step_map.clear()
