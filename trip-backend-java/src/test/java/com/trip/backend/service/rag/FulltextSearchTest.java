package com.trip.backend.service.rag;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * FulltextSearch 测试
 */
class FulltextSearchTest {

    // FulltextSearch 需要集成测试数据库
    @Test
    void testSearchWithChinese() {
        // TODO: 集成测试
    }

    @Test
    void testFallbackToLike() {
        // TODO: 验证全文失败时降级到 LIKE
    }
}
