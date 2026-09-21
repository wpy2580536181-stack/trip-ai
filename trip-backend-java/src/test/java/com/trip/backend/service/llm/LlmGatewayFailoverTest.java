package com.trip.backend.service.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.agent.tool.ToolExecutionRequest;
import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.data.message.ToolExecutionResultMessage;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * J-D1x LlmGateway 补全：failover + tool 消息解析 判定。
 *
 * 判定：
 *  1. mock 主 provider 超时 → fallback provider 被调用并返回结果（真实验证超时-fallback 链路）。
 *  2. 连续 3 次失败 → DEGRADED；恢复窗口后 → HEALTHY。
 *  3. tool 角色消息正确转 ToolExecutionResultMessage；带 tool_calls 的响应参数正确反序列化；
 *     ToolSpec.parametersSchema 正确转成 Langchain4j JsonObjectSchema。
 *
 * 不用 Mockito（JDK26 不兼容），用真实组件 + 自写 lambda。
 */
class LlmGatewayFailoverTest {

    private ProviderConfig minimalConfig() {
        ProviderConfig config = new ProviderConfig();
        config.setProviders(Map.of(
            "deepseek", props("sk-ds"),
            "kimi", props("sk-kimi"),
            "agnese", props("sk-ag")
        ));
        return config;
    }

    private ProviderConfig.ProviderProperties props(String key) {
        ProviderConfig.ProviderProperties p = new ProviderConfig.ProviderProperties();
        p.setApiKey(key);
        p.setBaseUrl("http://localhost:1/v1");
        p.setModel("test-model");
        return p;
    }

    // ---- 判定 1：主超时 → fallback 成功 ----
    @Test
    void primaryTimeoutFallsBackToSecondaryProvider() throws Exception {
        ProviderHealthRegistry registry = new ProviderHealthRegistry(60_000);
        ProviderConfig config = minimalConfig();
        ProviderRouter router = new ProviderRouter(config, registry);
        ObjectMapper om = new ObjectMapper();
        Langchain4jLlmClient dummyClient = new Langchain4jLlmClient(config, registry, om);
        // 超时设 1s（生产默认 15s，这里走注入）
        LlmGateway gateway = new LlmGateway(config, router, dummyClient, registry, 1);

        AtomicInteger primaryCalls = new AtomicInteger();
        AtomicInteger fallbackCalls = new AtomicInteger();
        AtomicReference<ProviderId> primaryUsed = new AtomicReference<>();
        AtomicReference<ProviderId> fallbackUsed = new AtomicReference<>();

        LlmClient.ChatResponse result = gateway.callWithFallback(
            Scenario.CHAT,
            provider -> {
                primaryCalls.incrementAndGet();
                primaryUsed.set(provider);
                try {
                    Thread.sleep(1500); // 超过 1s 超时
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
                return new LlmClient.ChatResponse("primary", List.of(), null);
            },
            provider -> {
                fallbackCalls.incrementAndGet();
                fallbackUsed.set(provider);
                return new LlmClient.ChatResponse("fallback", List.of(), null);
            });

        // CHAT 优先级 agnese → kimi → deepseek
        assertEquals("fallback", result.content(), "应返回 fallback 结果");
        assertEquals(1, primaryCalls.get(), "主 provider 应被调用一次");
        assertEquals(1, fallbackCalls.get(), "fallback provider 应被调用一次");
        assertEquals(ProviderId.AGNESE, primaryUsed.get(), "主 provider 应是 CHAT 首选 AGNESE");
        assertEquals(ProviderId.KIMI, fallbackUsed.get(), "fallback 应是次选 KIMI");
        // 主 provider 超时被 recordFailure（单次未到 3 次阈值，仍 HEALTHY；fallback 成功也已 recordSuccess）
        assertEquals(HealthState.HEALTHY, registry.getHealthState(ProviderId.AGNESE));
        assertEquals(HealthState.HEALTHY, registry.getHealthState(ProviderId.KIMI));
    }

    // ---- 判定 2：3 次失败 → DEGRADED；恢复窗口后 → HEALTHY ----
    @Test
    void threeFailuresDegradeAndRecoverAfterWindow() throws Exception {
        // 恢复窗口 200ms（生产 60s，注入短窗口验证）
        ProviderHealthRegistry registry = new ProviderHealthRegistry(200);

        registry.recordFailure(ProviderId.DEEPSEEK);
        registry.recordFailure(ProviderId.DEEPSEEK);
        assertEquals(HealthState.HEALTHY, registry.getHealthState(ProviderId.DEEPSEEK),
            "2 次失败未到阈值仍 HEALTHY");

        registry.recordFailure(ProviderId.DEEPSEEK);
        assertEquals(HealthState.DEGRADED, registry.getHealthState(ProviderId.DEEPSEEK),
            "连续 3 次失败 → DEGRADED");

        // 继续失败到 5 次 → DOWN
        registry.recordFailure(ProviderId.DEEPSEEK);
        registry.recordFailure(ProviderId.DEEPSEEK);
        assertEquals(HealthState.DOWN, registry.getHealthState(ProviderId.DEEPSEEK),
            "连续 5 次失败 → DOWN");

        Thread.sleep(250); // 超过恢复窗口
        assertEquals(HealthState.HEALTHY, registry.getHealthState(ProviderId.DEEPSEEK),
            "恢复窗口后自动回 HEALTHY");
    }

    // ---- 判定 3a：tool 角色消息 → ToolExecutionResultMessage ----
    @Test
    void toolMessageConvertedToToolExecutionResultMessage() {
        ProviderHealthRegistry registry = new ProviderHealthRegistry(60_000);
        Langchain4jLlmClient client = new Langchain4jLlmClient(minimalConfig(), registry, new ObjectMapper());

        LlmClient.ChatMessage userMsg = LlmClient.ChatMessage.of("user", "帮我找酒店");
        LlmClient.ChatMessage toolMsg = LlmClient.ChatMessage.toolResult(
            "call_42", "search_hotels", "{\"hotels\":[\"王府井\"]}");

        List<dev.langchain4j.data.message.ChatMessage> converted =
            client.toLangchainMessages(List.of(userMsg, toolMsg));

        assertEquals(2, converted.size());
        assertTrue(converted.get(1) instanceof ToolExecutionResultMessage,
            "tool 角色消息应转成 ToolExecutionResultMessage");
        ToolExecutionResultMessage trm = (ToolExecutionResultMessage) converted.get(1);
        assertEquals("call_42", trm.id());
        assertEquals("search_hotels", trm.toolName());
        assertTrue(trm.text().contains("王府井"));
    }

    // ---- 判定 3b：tool_calls 响应参数反序列化 ----
    @Test
    void toolCallsArgumentsDeserializedFromAiMessage() {
        ProviderHealthRegistry registry = new ProviderHealthRegistry(60_000);
        Langchain4jLlmClient client = new Langchain4jLlmClient(minimalConfig(), registry, new ObjectMapper());

        ToolExecutionRequest req = ToolExecutionRequest.builder()
            .name("search_hotels")
            .arguments("{\"city\":\"北京\",\"max_price\":800}")
            .build();
        AiMessage aiMessage = AiMessage.from(List.of(req));

        List<LlmClient.ToolCall> calls = client.extractToolCalls(aiMessage);

        assertEquals(1, calls.size());
        assertEquals("search_hotels", calls.get(0).name());
        assertTrue(calls.get(0).arguments().contains("\"city\":\"北京\""),
            "arguments 应原样保留 JSON 供工具反序列化: " + calls.get(0).arguments());
    }

    // ---- 判定 3c：parametersSchema → JsonObjectSchema ----
    @Test
    void toolParametersSchemaParsedIntoJsonObjectSchema() {
        ProviderHealthRegistry registry = new ProviderHealthRegistry(60_000);
        Langchain4jLlmClient client = new Langchain4jLlmClient(minimalConfig(), registry, new ObjectMapper());

        LlmClient.ToolSpec spec = new LlmClient.ToolSpec(
            "search_hotels",
            "搜索酒店",
            "{\"type\":\"object\","
                + "\"properties\":{"
                + "\"city\":{\"type\":\"string\",\"description\":\"城市名\"},"
                + "\"max_price\":{\"type\":\"integer\",\"description\":\"最高价\"}"
                + "},"
                + "\"required\":[\"city\"]}"
        );

        ToolSpecification ts = client.toToolSpecification(spec);

        assertEquals("search_hotels", ts.name());
        assertNotNull(ts.parameters(), "parametersSchema 非空时应生成 JsonObjectSchema");
        assertTrue(ts.parameters().properties().containsKey("city"), "properties 应含 city");
        assertTrue(ts.parameters().properties().containsKey("max_price"), "properties 应含 max_price");
        assertTrue(ts.parameters().required().contains("city"), "required 应含 city");
    }
}
