package com.trip.backend.service.llm;

import org.springframework.stereotype.Component;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

/**
 * LLM Gateway（对应 Python config/llm.py + provider_router/）
 * - Provider 路由
 * - 超时控制（15s，对应 Python asyncio.wait_for timeout_s=15）
 * - Fallback 机制（主 provider 超时/失败 → 切备用 provider）
 * - Token 记账
 */
@Component
public class LlmGateway {

    private final ProviderConfig config;
    private final ProviderRouter providerRouter;
    private final Langchain4jLlmClient llmClient;
    private final ProviderHealthRegistry healthRegistry;

    // 超时配置（对齐 Python call_with_fallback timeout_s=15.0）
    private static final long DEFAULT_TIMEOUT_SECONDS = 15;

    private final long timeoutSeconds;

    // 虚拟线程执行器：每次 LLM 调用一个虚拟线程，超时后 cancel
    private static final ExecutorService LLM_EXECUTOR = Executors.newThreadPerTaskExecutor(
        Thread.ofVirtual().name("llm-call-", 0).factory());

    public LlmGateway(ProviderConfig config,
                     ProviderRouter providerRouter,
                     Langchain4jLlmClient llmClient,
                     ProviderHealthRegistry healthRegistry) {
        this(config, providerRouter, llmClient, healthRegistry, DEFAULT_TIMEOUT_SECONDS);
    }

    /** 测试可注入更短的超时，快速验证超时-fallback 路径。 */
    LlmGateway(ProviderConfig config,
               ProviderRouter providerRouter,
               Langchain4jLlmClient llmClient,
               ProviderHealthRegistry healthRegistry,
               long timeoutSeconds) {
        this.config = config;
        this.providerRouter = providerRouter;
        this.llmClient = llmClient;
        this.healthRegistry = healthRegistry;
        this.timeoutSeconds = timeoutSeconds;
    }

    /**
     * 带 fallback 和超时的调用（对应 Python call_with_fallback）。
     * primary / fallback 两侧都套 15s 超时；主侧超时或异常 → 切备用 provider。
     */
    public LlmClient.ChatResponse callWithFallback(
            Scenario scenario,
            java.util.function.Function<ProviderId, LlmClient.ChatResponse> primaryFn,
            java.util.function.Function<ProviderId, LlmClient.ChatResponse> fallbackFn) {

        return providerRouter.executeWithFallback(scenario,
            provider -> withTimeout(() -> primaryFn.apply(provider)),
            provider -> fallbackFn != null ? withTimeout(() -> fallbackFn.apply(provider)) : null
        );
    }

    /**
     * 非流式调用（自动路由）
     */
    public LlmClient.ChatResponse invoke(Scenario scenario, java.util.List<LlmClient.ChatMessage> messages) {
        return invoke(scenario, messages, List.of());
    }

    /**
     * 非流式调用（带工具）
     *
     * primary/fallback 分别按 router 选出的 provider 调用（invokeAs），
     * 真正实现"主 provider 挂 → 切备用 provider"，而非同一个 client 重复调用。
     */
    public LlmClient.ChatResponse invoke(Scenario scenario,
                                        java.util.List<LlmClient.ChatMessage> messages,
                                        java.util.List<LlmClient.ToolSpec> tools) {
        return callWithFallback(
            scenario,
            provider -> llmClient.invokeAs(provider, messages, tools),
            provider -> llmClient.invokeAs(provider, messages, tools)
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
     *
     * 备用路由由 ProviderRouter.selectFallback 在调用时决定（按 scenario 优先级跳过故障 provider），
     * 这里返回同一 client 实现——它会按 provider 参数建不同 provider 的 model。
     */
    public LlmClient getFallbackClient() {
        return llmClient;
    }

    /**
     * 带 15s 超时地执行一段 LLM 调用；超时抛 {@link LlmTimeoutException}（对齐 Python TimeoutError）。
     */
    private LlmClient.ChatResponse withTimeout(Supplier<LlmClient.ChatResponse> task) {
        Future<LlmClient.ChatResponse> future = LLM_EXECUTOR.submit(task::get);
        try {
            return future.get(timeoutSeconds, TimeUnit.SECONDS);
        } catch (TimeoutException e) {
            future.cancel(true);
            throw new LlmTimeoutException("LLM call timed out after " + timeoutSeconds + "s", e);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new LlmTimeoutException("LLM call interrupted", e);
        } catch (ExecutionException e) {
            Throwable cause = e.getCause();
            if (cause instanceof RuntimeException re) {
                throw re;
            }
            throw new RuntimeException(cause);
        }
    }
}
