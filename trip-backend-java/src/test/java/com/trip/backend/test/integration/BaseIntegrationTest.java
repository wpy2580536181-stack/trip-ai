package com.trip.backend.test.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * 集成测试基类
 *
 * 提供：
 * - MockMvc 测试客户端
 * - ObjectMapper JSON 序列化
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
public abstract class BaseIntegrationTest {

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected ObjectMapper objectMapper;

    /**
     * 断言响应状态码
     */
    protected void assertStatusCode(Map<String, Object> response, int expectedCode) {
        Integer code = (Integer) response.get("code");
        if (code == null) {
            // Format A response
            Boolean success = (Boolean) response.get("success");
            if (expectedCode == 200 || expectedCode == 201) {
                assert success != null && success : "Expected success=true, got: " + response;
            }
        } else {
            assert code.equals(expectedCode) : "Expected code=" + expectedCode + ", got: " + code;
        }
    }

    /**
     * 断言响应包含指定键
     */
    protected void assertResponseContains(Map<String, Object> response, String key) {
        assert response.containsKey(key) : "Expected response to contain key: " + key;
    }

    /**
     * 断言响应 data 不为空
     */
    protected void assertDataNotNull(Map<String, Object> response) {
        assert response.get("data") != null : "Expected data to be not null";
    }
}
