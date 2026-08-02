package com.trip.backend.service.rag;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * RetrievalPipeline 集成测试
 */
class RetrievalPipelineTest {

    // RetrievalPipeline 需要集成测试数据库
    @Test
    void testPipelineWithBothSources() {
        // TODO: 集成测试：双路召回 + RRF 融合
    }

    @Test
    void testFallbackChain() {
        // TODO: 验证降级链：全文失败→LIKE；RRF 失败→普通 RRF
    }

    @Test
    void testLimitTruncation() {
        // TODO: 验证 limit=5 截断
    }
}
