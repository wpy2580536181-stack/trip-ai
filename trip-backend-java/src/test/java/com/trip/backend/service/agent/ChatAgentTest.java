package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import com.trip.backend.service.chat.EventSink;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * ChatAgent 测试
 *
 * 对应 Python test_chat_agent.py
 *
 * 验证：
 * - 四工具触发与降级
 * - 卡片事件结构
 * - usage 合并
 */
class ChatAgentTest {

    @Test
    void testToolTriggerPlan() {
        // TODO: D8 实现后补充
    }

    @Test
    void testToolTriggerModify() {
        // TODO: D8 实现后补充
    }

    @Test
    void testToolTriggerPatch() {
        // TODO: D8 实现后补充
    }

    @Test
    void testSelectSkill() {
        // TODO: D8 实现后补充
    }

    @Test
    void testCardEventStructure() {
        // TODO: D8 实现后补充
    }

    @Test
    void testUsageMerge() {
        // TODO: D8 实现后补充
    }
}
