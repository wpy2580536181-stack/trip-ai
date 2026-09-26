package com.trip.backend.eval.agents;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.eval.types.AgentOutput;
import com.trip.backend.eval.types.Fixture;
import com.trip.backend.eval.types.TokenUsage;
import com.trip.backend.eval.types.ToolCall;
import com.trip.backend.eval.types.ToolCall;
import org.springframework.http.*;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.net.URI;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Real Agent（调用真实后端 API）
 * <p>
 * 调用 /api/trip/recommend 或 /api/trip/recommend-stream
 */
public class RealAgent {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();
    private static final String DEFAULT_BASE_URL = "http://localhost:8000";
    private final String baseUrl;
    private final RestTemplate restTemplate;
    private final String authToken;

    /**
     * 构造函数（无认证）
     *
     * @param baseUrl 后端基础 URL（如 http://localhost:8000）
     */
    public RealAgent(String baseUrl) {
        this(baseUrl, null);
    }

    /**
     * 构造函数（带认证）
     *
     * @param baseUrl   后端基础 URL
     * @param authToken JWT token（可选）
     */
    public RealAgent(String baseUrl, String authToken) {
        this.baseUrl = baseUrl != null ? baseUrl : DEFAULT_BASE_URL;
        this.restTemplate = new RestTemplate();
        this.authToken = authToken;
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
            // 对话 / 拒答 / 多轮类（json_valid=false）走 chat SSE
            if (!fixture.getExpected().isJsonValid()) {
                return runChat(fixture);
            }
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

    private AgentOutput runChat(Fixture fixture) {
        long start = System.currentTimeMillis();
        try {
            Long convId = null;
            // 播种多轮历史中的 user 消息（assistant 历史由后端在同一会话中真实生成）
            for (Map<String, Object> h : fixture.getInput().getHistory()) {
                if ("user".equals(h.get("role"))) {
                    ChatRound seed = sendChatRound(String.valueOf(h.get("content")), convId);
                    convId = seed.convId;
                }
            }
            ChatRound last = sendChatRound(fixture.getInput().getMessage(), convId);

            AgentOutput output = new AgentOutput();
            output.setText(last.text);
            output.setJson(null);
            output.setToolCalls(last.toolCalls);
            output.setTokens(new TokenUsage(0, 0, 0, 0));
            output.setDurationMs((int) (System.currentTimeMillis() - start));
            return output;
        } catch (Exception e) {
            AgentOutput output = new AgentOutput();
            output.setError("chat failed: " + e.getMessage());
            output.setText("");
            output.setJson(null);
            output.setToolCalls(List.of());
            output.setDurationMs((int) (System.currentTimeMillis() - start));
            return output;
        }
    }

    /** 单轮 chat 往返结果。 */
    private static final class ChatRound {
        String text = "";
        Long convId;
        List<ToolCall> toolCalls = new ArrayList<>();
    }

    /** 发送一次 chat（SSE），解析文本、工具调用，并从响应头取 conversationId。 */
    private ChatRound sendChatRound(String message, Long convId) throws Exception {
        Map<String, Object> reqMap = new HashMap<>();
        reqMap.put("message", message);
        reqMap.put("conversationId", convId);
        String reqBody = OBJECT_MAPPER.writeValueAsString(reqMap);

        java.net.http.HttpRequest.Builder b = java.net.http.HttpRequest.newBuilder(
                URI.create(baseUrl + "/api/trip/chat"))
            .header("Content-Type", "application/json")
            .POST(java.net.http.HttpRequest.BodyPublishers.ofString(reqBody));
        if (authToken != null && !authToken.isEmpty()) {
            b.header("Authorization", "Bearer " + authToken);
        }
        java.net.http.HttpClient client = java.net.http.HttpClient.newBuilder()
            .connectTimeout(java.time.Duration.ofSeconds(10)).build();
        java.net.http.HttpResponse<String> resp = client.send(b.build(),
            java.net.http.HttpResponse.BodyHandlers.ofString());

        ChatRound round = new ChatRound();
        round.convId = resp.headers().firstValue("X-Conversation-Id")
            .map(Long::valueOf).orElse(convId);

        StringBuilder text = new StringBuilder();
        for (String line : resp.body().split("\n")) {
            String t = line.trim();
            if (!t.startsWith("data:")) continue;
            String payload = t.substring(5).trim();
            if (!payload.startsWith("{")) continue;
            try {
                Map<String, Object> ev = OBJECT_MAPPER.readValue(payload,
                    new com.fasterxml.jackson.core.type.TypeReference<Map<String, Object>>() {});
                if (ev.get("content") instanceof String c) text.append(c);
                Object tc = ev.get("toolCalls");
                if (tc instanceof List<?> tcl) {
                    for (Object o : tcl) {
                        if (o instanceof Map<?, ?> om && om.get("name") != null) {
                            round.toolCalls.add(new ToolCall(om.get("name").toString(), null, null, null));
                        }
                    }
                }
            } catch (Exception ignore) {}
        }
        round.text = text.toString();
        return round;
    }

    /**
     * 同步调用（非流式）
     */
    private AgentOutput runSync(String endpoint, Map<String, Object> requestBody, Fixture fixture) {
        long startTime = System.currentTimeMillis();

        try {
            HttpHeaders headers = createHeaders();

            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(requestBody, headers);
            ResponseEntity<Map> response = restTemplate.exchange(
                URI.create(baseUrl + endpoint),
                HttpMethod.POST,
                entity,
                Map.class
            );

            long durationMs = System.currentTimeMillis() - startTime;

            AgentOutput output = new AgentOutput();
            Map<String, Object> body = response.getBody();
            // 解包：后端统一信封 {success, data}，evaluator 在 data 顶层找字段
            Object data = (body != null && body.get("data") != null) ? body.get("data") : body;
            if (data instanceof Map) {
                @SuppressWarnings("unchecked")
                Map<String, Object> dataMap = (Map<String, Object>) data;
                output.setJson(dataMap);
            } else {
                output.setJson(body);
            }
            try {
                output.setText(OBJECT_MAPPER.writeValueAsString(data));
            } catch (Exception e) {
                output.setText(data != null ? data.toString() : "");
            }

            // 解析工具调用审计 data.toolCalls=[{name:...}]
            List<ToolCall> parsedCalls = new ArrayList<>();
            if (data instanceof Map) {
                Object tcs = ((Map<?, ?>) data).get("toolCalls");
                if (tcs instanceof List) {
                    for (Object o : (List<?>) tcs) {
                        if (o instanceof Map && ((Map<?, ?>) o).get("name") != null) {
                            parsedCalls.add(new ToolCall(
                                ((Map<?, ?>) o).get("name").toString(), null, null, null));
                        }
                    }
                }
            }
            output.setToolCalls(parsedCalls);

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
     * 创建请求头
     */
    private HttpHeaders createHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        if (authToken != null && !authToken.isEmpty()) {
            headers.setBearerAuth(authToken);
        }
        return headers;
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
