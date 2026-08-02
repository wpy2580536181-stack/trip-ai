package com.trip.backend.service.llm;

import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

/**
 * LLM Gateway（对应 Python config/llm.py + provider_router/）
 * - Provider 路由
 * - 超时控制（15s）
 * - Fallback 机制
 * - Token 记账
 */
@Component
public class LlmGateway {

    private final ProviderConfig config;
    private final ProviderRouter providerRouter;
    private final Langchain4jLlmClient llmClient;
    private final ProviderHealthRegistry healthRegistry;

    // 超时配置
    private static final long TIMEOUT_SECONDS = 15;

    public LlmGateway(ProviderConfig config,
                     ProviderRouter providerRouter,
                     Langchain4jLlmClient llmClient,
                     ProviderHealthRegistry healthRegistry) {
        this.config = config;
        this.providerRouter = providerRouter;
        this.llmClient = llmClient;
        this.healthRegistry = healthRegistry;
    }

    /**
     * 带 fallback 和超时的调用
     */
    public LlmClient.ChatResponse callWithFallback(
            Scenario scenario,
            java.util.function.Function<ProviderId, LlmClient.ChatResponse> primaryFn,
            java.util.function.Function<ProviderId, LlmClient.ChatResponse> fallbackFn) {

        return providerRouter.executeWithFallback(scenario,
            provider -> {
                try {
                    // TODO: 添加超时控制（15s）
                    return primaryFn.apply(provider);
                } catch (Exception e) {
                    healthRegistry.recordFailure(provider);
                    throw e;
                }
            },
            fallbackFn
        );
    }

    /**
     * 非流式调用（自动路由）
     */
    public LlmClient.ChatResponse invoke(Scenario scenario, java.util.List<LlmClient.ChatMessage> messages) {
        return callWithFallback(
            scenario,
            provider -> llmClient.invoke(messages),
            provider -> llmClient.invoke(messages)
        );
    }

    /**
     * 非流式调用（带工具）
     */
    public LlmClient.ChatResponse invoke(Scenario scenario,
                                        java.util.List<LlmClient.ChatMessage> messages,
                                        java.util.List<LlmClient.ToolSpec> tools) {
        return callWithFallback(
            scenario,
            provider -> llmClient.invoke(messages, tools),
            provider -> llmClient.invoke(messages, tools)
        );
    }

    /**
     * 流式调用
     */
    public void stream(Scenario scenario,
                      java.util.List<LlmClient.ChatMessage> messages,
                      LlmClient.StreamHandler handler) {
        stream(scenario, messages, List.of(), handler);
    }

    /**
     * 流式调用（带工具）
     */
    public void stream(Scenario scenario,
                      java.util.List<LlmClient.ChatMessage> messages,
                      java.util.List<LlmClient.ToolSpec> tools,
                      LlmClient.StreamHandler handler) {

        ProviderId provider = providerRouter.select(scenario);

        try {
            llmClient.stream(messages, tools, new LlmClient.StreamHandler() {
                @Override
                public void onPartialResponse(String text) {
                    handler.onPartialResponse(text);
                }

                @Override
                public void onToolCallDelta(String toolCallJson) {
                    handler.onToolCallDelta(toolCallJson);
                }

                @Override
                public void onComplete(LlmClient.ChatResponse response) {
                    healthRegistry.recordSuccess(provider);
                    handler.onComplete(response);
                }

                @Override
                public void onError(Throwable error) {
                    healthRegistry.recordFailure(provider);
                    handler.onError(error);
                }
            });
        } catch (Exception e) {
            healthRegistry.recordFailure(provider);
            handler.onError(e);
        }
    }

    /**
     * 获取主 LLM（用于 AgentEngine）
     */
    public LlmClient getPrimaryClient() {
        return llmClient;
    }

    /**
     * 获取备用 LLM
     */
    public LlmClient getFallbackClient() {
        // TODO: 实现 fallback client
        return llmClient;
    }
}
