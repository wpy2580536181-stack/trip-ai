package com.trip.backend.service.rag;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * RetrievalEvalTest - 检索评估测试
 *
 * 对应 Python eval/retrieval/run.py
 *
 * 验证：
 * - Hit@K ≥ 基线
 * - MRR ≥ 基线
 */
class RetrievalEvalTest {

    @Test
    void testHitAtK() {
        // TODO: C3 实现后补充（需要 eval fixture）
    }

    @Test
    void testMRR() {
        // TODO: C3 实现后补充
    }

    @Test
    void testFourWayVsTwoWay() {
        // TODO: C3 实现后补充
    }
}
