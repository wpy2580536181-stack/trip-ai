package com.trip.backend.eval;

import com.trip.backend.eval.util.TestAuthHelper;
import com.trip.backend.eval.util.SseTestHelper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;

/**
 * SSE 流式接口测试
 */
class SseStreamTest {

    @Test
    void testSseStream() throws Exception {
        String token = TestAuthHelper.getTestToken();
        assertNotNull(token);

        System.out.println("\n=== SSE 流测试 ===\n");

        // 测试 SSE 连接
        SseTestHelper.testSseConnection("http://localhost:8000", token);

        System.out.println("\n=== SSE 测试完成 ===");
    }
}
