package com.trip.backend.eval.agents;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.TokenUsage;
import com.trip.backend.eval.types.ToolCall;
import org.springframework.http.*;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.net.URI;
import java.util.List;
import java.util.Map;

/**
 * Real Agent（调用真实后端 API）
 * <p>
 * 调用 /api/trip/recommend 或 /api/trip/recommend-stream
 */
public class RealAgent {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private final String baseUrl;
    private final RestTemplate restTemplate;

    /**
     * 构造函数
     *
     * @param baseUrl 后端基础 URL（如 http://localhost:8080）
     */
    public RealAgent(String baseUrl) {
        this.baseUrl = baseUrl;
        this.restTemplate = new RestTemplate();
    }

    /**
     * 执行真实 agent（调用后端 API）
     *
     * @param fixture  测试用例
     * @param useStream 是否使用流式接口
     * @return AgentOutput
     */
    public AgentOutput run(Fixture fixture, boolean useStream) {
        try {
            String endpoint = useStream ? "/api/trip/recommend-stream" : "/api/trip/recommend";

            // 构建请求体
            Map<String, Object> requestBody = Map.of(
                "city", fixture.getExpected().getCity(),
                "days", fixture.getExpected().getDays(),
                "budget", 3000,
                "message", fixture.getInput().getMessage()
            );

            if (useStream) {
                return runStream(endpoint, requestBody, fixture);
            } else {
                return runSync(endpoint, requestBody, fixture);
            }

        } catch (Exception e) {
            // 后端调用失败，返回错误
            AgentOutput output = new AgentOutput();
            output.setError("Real agent failed: " + e.getMessage());
            output.setText("");
            output.setJson(null);
            output.setToolCalls(List.of());
            output.setTokens(new TokenUsage(0, 0, 0, 0));
            output.setDurationMs(0);
            return output;
        }
    }

    /**
     * 同步调用（非流式）
     */
    private AgentOutput runSync(String endpoint, Map<String, Object> requestBody, Fixture fixture) {
        long startTime = System.currentTimeMillis();

        try {
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            // TODO: 添加认证头（需要测试 JWT token）
            // headers.setBearerAuth(testToken);

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(requestBody, headers);
            ResponseEntity<Map> response = restTemplate.exchange(
                URI.create(baseUrl + endpoint),
                HttpMethod.POST,
                entity,
                Map.class
            );

            long durationMs = System.currentTimeMillis() - startTime;

            AgentOutput output = new AgentOutput();
            output.setJson(response.getBody());
            try {
                output.setText(OBJECT_MAPPER.writeValueAsString(response.getBody()));
            } catch (Exception e) {
                output.setText(response.getBody() != null ? response.getBody().toString() : "");
            }
            output.setToolCalls(List.of());  // TODO: 从响应中提取 tool_calls
            output.setTokens(new TokenUsage(0, 0, 0, 0));  // TODO: 从响应头或响应体中提取
            output.setDurationMs((int) durationMs);

            return output;

        } catch (RestClientException e) {
            long durationMs = System.currentTimeMillis() - startTime;
            AgentOutput output = new AgentOutput();
            output.setError("HTTP call failed: " + e.getMessage());
            output.setText("");
            output.setDurationMs((int) durationMs);
            return output;
        }
    }

    /**
     * 流式调用（SSE）
     */
    private AgentOutput runStream(String endpoint, Map<String, Object> requestBody, Fixture fixture) {
        long startTime = System.currentTimeMillis();

        try {
            // TODO: 实现 SSE 流式调用
            // 需要解析 SSE 格式：
            // event: message
            // data: {...}
            //
            // event: done
            // data: {"status": "complete"}

            // 暂时回退到同步调用
            return runSync(endpoint.replace("-stream", ""), requestBody, fixture);

        } catch (Exception e) {
            long durationMs = System.currentTimeMillis() - startTime;
            AgentOutput output = new AgentOutput();
            output.setError("SSE call failed: " + e.getMessage());
            output.setText("");
            output.setDurationMs((int) durationMs);
            return output;
        }
    }
}
