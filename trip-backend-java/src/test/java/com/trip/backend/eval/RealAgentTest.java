package com.trip.backend.eval;

import com.trip.backend.eval.util.TestAuthHelper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Real Agent 集成测试
 */
class RealAgentTest {

    @Test
    void testGetTestToken() {
        String token = TestAuthHelper.getTestToken();
        assertNotNull(token, "应该能获取到测试 token");
        assertTrue(token.length() > 50, "token 长度应该 > 50");
        System.out.println("Token: " + token.substring(0, 20) + "...");
    }
}
