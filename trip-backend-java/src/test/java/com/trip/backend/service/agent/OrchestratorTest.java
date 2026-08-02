package com.trip.backend.service.agent;

import com.trip.backend.service.agent.dto.*;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Orchestrator 测试
 *
 * 对应 Python test_orchestrator.py
 *
 * 验证：
 * - 三阶段顺序（research → plan → review）
 * - progress 事件序列
 * - review 失败 → feedback 注入重跑 ≤2 次
 * - 预算超 15% 打回
 * - modify 局部/全量模式
 */
class OrchestratorTest {

    @Test
    void testThreeStageSequence() {
        // TODO: D7 实现后补充
    }

    @Test
    void testProgressEvents() {
        // TODO: D7 实现后补充
    }

    @Test
    void testReviewRetryWithFeedback() {
        // TODO: D7 实现后补充
    }

    @Test
    void testBudgetExceededReject() {
        // TODO: D7 实现后补充
    }

    @Test
    void testModifyPartialMode() {
        // TODO: D7 实现后补充
    }

    @Test
    void testModifyMergePreservesUnchangedDays() {
        // TODO: D7 实现后补充
    }
}
