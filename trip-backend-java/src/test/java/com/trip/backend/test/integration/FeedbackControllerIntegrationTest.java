package com.trip.backend.test.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;

import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/**
 * 反馈控制器集成测试
 *
 * 对标 Python: tests/test_feedback_controller.py
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
public class FeedbackControllerIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    /**
     * 辅助方法：发送 POST 请求
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> performPost(String url, Object body) throws Exception {
        String json = objectMapper.writeValueAsString(body);
        MvcResult result = mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(url)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json))
                .andReturn();

        String content = result.getResponse().getContentAsString();
        return objectMapper.readValue(content, Map.class);
    }

    /**
     * 辅助方法：注册用户并获取 token
     */
    private String registerAndLogin() throws Exception {
        // 注册
        Map<String, Object> registerRequest = Map.of(
            "username", "feedbackuser",
            "email", "feedback@example.com",
            "password", "Test@123"
        );
        Map<String, Object> registerResponse = performPost("/api/user/register", registerRequest);
        Map<String, Object> registerData = (Map<String, Object>) registerResponse.get("data");

        // 登录
        Map<String, Object> loginRequest = Map.of(
            "identifier", "feedbackuser",
            "password", "Test@123"
        );
        Map<String, Object> loginResponse = performPost("/api/user/login", loginRequest);
        Map<String, Object> loginData = (Map<String, Object>) loginResponse.get("data");

        return (String) loginData.get("token");
    }

    /**
     * 测试提交反馈
     */
    @Test
    void testSubmitFeedback() throws Exception {
        String token = registerAndLogin();

        // 准备反馈请求
        Map<String, Object> request = Map.of(
            "messageId", 1,
            "conversationId", 1,
            "rating", 5,
            "comment", "非常棒的推荐！",
            "tags", new String[]{"推荐", "实用"}
        );

        // 发送 POST /api/feedback
        Map<String, Object> response = performPost("/api/feedback", request);

        // 断言：响应格式 B（code=200 或 201）
        if (response.containsKey("code")) {
            Integer code = (Integer) response.get("code");
            assert code.equals(200) || code.equals(201) :
                "Expected code=200 or 201, got: " + code;
        } else {
            assert (Boolean) response.getOrDefault("success", false) :
                "Expected success=true";
        }

        System.out.println("✅ testSubmitFeedback passed");
    }

    /**
     * 测试获取反馈列表
     */
    @Test
    void testGetFeedbackList() throws Exception {
        String token = registerAndLogin();

        // 发送 GET /api/feedback
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/feedback")
                        .header("Authorization", "Bearer " + token)
                        .param("page", "1")
                        .param("pageSize", "10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200));

        System.out.println("✅ testGetFeedbackList passed");
    }

    /**
     * 测试获取消息统计
     */
    @Test
    void testGetMessageStats() throws Exception {
        // 发送 GET /api/feedback/message/1
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/feedback/message/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200));

        System.out.println("✅ testGetMessageStats passed");
    }
}
