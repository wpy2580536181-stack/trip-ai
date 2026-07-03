"""测试 Agent 模块的导入和结构。

验证 T06 任务创建的模块是否能正常导入和实例化。
"""

import sys
import unittest
from unittest.mock import Mock, MagicMock, patch

# Mock 重型依赖
sys.modules["torch"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()
sys.modules["chromadb"] = MagicMock()


class TestAgentImports(unittest.TestCase):
    """测试 Agent 模块导入。"""
    
    def test_state_module(self):
        """测试 state 模块。"""
        from src.services.agent.state import PlannerState
        self.assertIsNotNone(PlannerState)
        print("✓ state.py - PlannerState 可导入")
    
    def test_types_module(self):
        """测试 types 模块。"""
        from src.services.agent.types import ResearchBundle, TokenUsage, StepInput
        self.assertIsNotNone(ResearchBundle)
        print("✓ types.py - ResearchBundle, TokenUsage, StepInput 可导入")
    
    def test_agent_engine_module(self):
        """测试 agent_engine 模块。"""
        from src.services.agent.agent_engine import AgentEngine, get_agent_engine
        self.assertIsNotNone(AgentEngine)
        self.assertIsNotNone(get_agent_engine)
        print("✓ agent_engine.py - AgentEngine, get_agent_engine 可导入")
    
    def test_trace_recorder_module(self):
        """测试 trace_recorder 模块。"""
        from src.services.agent.trace_recorder import TraceRecorder
        self.assertIsNotNone(TraceRecorder)
        print("✓ trace_recorder.py - TraceRecorder 可导入")
    
    def test_token_monitor_module(self):
        """测试 token_monitor 模块。"""
        from src.services.agent.token_monitor import TokenMonitor, token_monitor
        self.assertIsNotNone(TokenMonitor)
        self.assertIsNotNone(token_monitor)
        print("✓ token_monitor.py - TokenMonitor, token_monitor 可导入")


if __name__ == "__main__":
    unittest.main()
