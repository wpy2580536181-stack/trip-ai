"""测试 Agent 模块的导入和结构。

验证 T06 任务创建的模块是否能正常导入和实例化。
"""

import sys
import unittest
from unittest.mock import Mock, MagicMock, patch


class TestAgentImports(unittest.TestCase):
    """测试 Agent 模块导入。"""

    # Modules that need to be mocked for agent imports
    HEAVY_MODULES = ["torch", "sentence_transformers", "chromadb"]

    def setUp(self):
        """Save original sys.modules state before each test."""
        self._saved_modules = {}
        for mod in self.HEAVY_MODULES:
            if mod in sys.modules:
                self._saved_modules[mod] = sys.modules[mod]
            sys.modules[mod] = MagicMock()

    def tearDown(self):
        """Restore original sys.modules state after each test."""
        for mod in self.HEAVY_MODULES:
            if mod in self._saved_modules:
                sys.modules[mod] = self._saved_modules[mod]
            else:
                # Remove mock if the module wasn't originally there
                sys.modules.pop(mod, None)

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
