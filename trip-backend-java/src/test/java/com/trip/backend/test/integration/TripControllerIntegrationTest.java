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
 * 行程控制器集成测试
 *
 * 对标 Python: tests/test_trip_service.py + test_trip_controller.py
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
public class TripControllerIntegrationTest {

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
            "username", "tripuser",
            "email", "trip@example.com",
            "password", "Test@123"
        );
        Map<String, Object> registerResponse = performPost("/api/user/register", registerRequest);
        Map<String, Object> registerData = (Map<String, Object>) registerResponse.get("data");

        // 登录
        Map<String, Object> loginRequest = Map.of(
            "identifier", "tripuser",
            "password", "Test@123"
        );
        Map<String, Object> loginResponse = performPost("/api/user/login", loginRequest);
        Map<String, Object> loginData = (Map<String, Object>) loginResponse.get("data");

        return (String) loginData.get("token");
    }

    /**
     * 测试创建行程推荐（recommend 接口）
     */
    @Test
    void testRecommendTrip() throws Exception {
        // 先注册登录
        registerAndLogin();

        // 准备推荐请求
        Map<String, Object> request = Map.of(
            "city", "成都",
            "days", 3,
            "budget", 5000,
            "from_city", "北京"
        );

        // 发送 POST /api/trip/recommend
        Map<String, Object> response = performPost("/api/trip/recommend", request);

        // 断言：响应格式 A（success=true）
        assert response.containsKey("success") : "Expected Format A (success)";
        assert (Boolean) response.get("success") : "Expected success=true";

        // 断言：data 包含行程信息
        Map<String, Object> data = (Map<String, Object>) response.get("data");
        assert data != null : "Expected data to be not null";
        assert data.containsKey("id") : "Expected data.id";
        assert data.containsKey("city") : "Expected data.city";

        System.out.println("✅ testRecommendTrip passed");
    }

    /**
     * 测试获取用户行程列表
     */
    @Test
    void testGetUserTrips() throws Exception {
        String token = registerAndLogin();

        // 发送 GET /api/trip/history
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/trip/history")
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200));

        System.out.println("✅ testGetUserTrips passed");
    }

    /**
     * 测试获取行程详情
     */
    @Test
    void testGetTripDetail() throws Exception {
        String token = registerAndLogin();

        // 先创建行程
        Map<String, Object> recommendRequest = Map.of(
            "city", "杭州",
            "days", 2,
            "budget", 3000
        );
        Map<String, Object> recommendResponse = performPost("/api/trip/recommend", recommendRequest);
        Map<String, Object> tripData = (Map<String, Object>) recommendResponse.get("data");
        Long tripId = (Long) tripData.get("id");

        // 获取行程详情
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get("/api/trip/" + tripId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(200))
                .andExpect(jsonPath("$.data.id").value(tripId));

        System.out.println("✅ testGetTripDetail passed");
    }
}
