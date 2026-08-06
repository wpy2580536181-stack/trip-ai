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
 * 用户控制器集成测试
 *
 * 对标 Python: tests/test_user_controller.py
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
public class UserControllerIntegrationTest {

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
     * 辅助方法：发送 GET 请求
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> performGet(String url) throws Exception {
        MvcResult result = mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get(url))
                .andReturn();

        String content = result.getResponse().getContentAsString();
        return objectMapper.readValue(content, Map.class);
    }

    /**
     * 测试用户注册成功
     */
    @Test
    void testRegisterSuccess() throws Exception {
        // 准备注册请求
        Map<String, Object> request = Map.of(
            "username", "testuser",
            "email", "test@example.com",
            "password", "Test@123",
            "nickname", "Test User"
        );

        // 发送 POST /api/user/register
        Map<String, Object> response = performPost("/api/user/register", request);

        // 断言：响应格式 A 或 B
        assert response.containsKey("success") || response.containsKey("code") :
            "Expected Format A (success) or Format B (code)";

        // 断言：成功标志
        if (response.containsKey("success")) {
            assert (Boolean) response.get("success") : "Expected success=true";
        } else {
            assert ((Integer) response.get("code")).equals(201) : "Expected code=201";
        }

        // 断言：data 包含用户信息
        Map<String, Object> data = (Map<String, Object>) response.get("data");
        assert data != null : "Expected data to be not null";
        assert data.containsKey("id") : "Expected data.id";
        assert data.containsKey("username") : "Expected data.username";
        assert "testuser".equals(data.get("username")) : "Expected username=testuser";

        System.out.println("✅ testRegisterSuccess passed");
    }

    /**
     * 测试用户登录成功
     */
    @Test
    void testLoginSuccess() throws Exception {
        // 先注册一个用户
        performPost("/api/user/register", Map.of(
            "username", "loginuser",
            "email", "login@example.com",
            "password", "Test@123"
        ));

        // 发送登录请求
        Map<String, Object> response = performPost("/api/user/login", Map.of(
            "identifier", "loginuser",
            "password", "Test@123"
        ));

        // 断言：响应格式 B（code=200）
        assert response.containsKey("code") : "Expected Format B (code)";
        assert ((Integer) response.get("code")).equals(200) : "Expected code=200";

        // 断言：data 包含 token
        Map<String, Object> data = (Map<String, Object>) response.get("data");
        assert data != null : "Expected data to be not null";
        assert data.containsKey("token") : "Expected data.token";

        System.out.println("✅ testLoginSuccess passed");
    }

    /**
     * 测试登录失败（密码错误）
     */
    @Test
    void testLoginFailureWrongPassword() throws Exception {
        // 先注册一个用户
        performPost("/api/user/register", Map.of(
            "username", "wrongpassuser",
            "email", "wrongpass@example.com",
            "password", "Test@123"
        ));

        // 发送错误密码的登录请求
        Map<String, Object> response = performPost("/api/user/login", Map.of(
            "identifier", "wrongpassuser",
            "password", "WrongPassword"
        ));

        // 断言：响应格式 B（code=401）
        assert response.containsKey("code") : "Expected Format B (code)";
        assert ((Integer) response.get("code")).equals(401) : "Expected code=401";

        System.out.println("✅ testLoginFailureWrongPassword passed");
    }

    /**
     * 测试重复用户名注册失败
     */
    @Test
    void testRegisterDuplicateUsername() throws Exception {
        // 注册第一个用户
        performPost("/api/user/register", Map.of(
            "username", "duplicate",
            "email", "dup1@example.com",
            "password", "Test@123"
        ));

        // 尝试用相同用户名注册
        Map<String, Object> response = performPost("/api/user/register", Map.of(
            "username", "duplicate",
            "email", "dup2@example.com",
            "password", "Test@456"
        ));

        // 断言：重复用户名应返回错误
        if (response.containsKey("success")) {
            assert !(Boolean) response.get("success") : "Expected success=false for duplicate username";
        } else {
            Integer code = (Integer) response.get("code");
            assert code != null && code >= 400 : "Expected error code >= 400, got: " + code;
        }

        System.out.println("✅ testRegisterDuplicateUsername passed");
    }
}
