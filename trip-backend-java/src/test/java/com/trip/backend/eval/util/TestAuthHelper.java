package com.trip.backend.eval.util;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.*;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

/**
 * 测试认证辅助工具
 */
public class TestAuthHelper {

    private static final String BASE_URL = "http://localhost:8000";
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final RestTemplate REST_TEMPLATE = new RestTemplate();

    /**
     * 注册测试用户并登录
     *
     * @return JWT token
     */
    public static String getTestToken() {
        try {
            // 1. 尝试注册（如果用户已存在会失败，忽略）
            registerTestUser();

            // 2. 登录获取 token
            return login();
        } catch (Exception e) {
            System.err.println("Failed to get test token: " + e.getMessage());
            return null;
        }
    }

    /**
     * 注册测试用户
     */
    private static void registerTestUser() {
        try {
            Map<String, Object> request = Map.of(
                "username", "eval_test_user",
                "email", "eval_test@example.com",
                "password", "EvalTest123!"
            );

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, createHeaders());
            ResponseEntity<Map> response = REST_TEMPLATE.exchange(
                BASE_URL + "/api/user/register",
                HttpMethod.POST,
                entity,
                Map.class
            );

            System.out.println("User registered: " + response.getStatusCode());
        } catch (Exception e) {
            // 用户可能已存在，忽略
            System.out.println("User registration skipped (may already exist): " + e.getMessage());
        }
    }

    /**
     * 登录获取 token
     */
    private static String login() {
        try {
            Map<String, Object> request = Map.of(
                "identifier", "eval_test_user",
                "password", "EvalTest123!"
            );

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, createHeaders());
            ResponseEntity<Map> response = REST_TEMPLATE.exchange(
                BASE_URL + "/api/user/login",
                HttpMethod.POST,
                entity,
                Map.class
            );

            Map<String, Object> body = response.getBody();
            if (body != null && body.containsKey("data")) {
                Map<String, Object> data = (Map<String, Object>) body.get("data");
                if (data != null && data.containsKey("token")) {
                    String token = (String) data.get("token");
                    System.out.println("Login successful, token length: " + token.length());
                    return token;
                }
            }

            throw new RuntimeException("No token in response");
        } catch (Exception e) {
            throw new RuntimeException("Login failed: " + e.getMessage(), e);
        }
    }

    /**
     * 创建请求头
     */
    private static HttpHeaders createHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }
}
