package com.trip.backend.service.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import dev.langchain4j.data.message.*;
import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.agent.tool.ToolSpecifications;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * langchain4j 实现的 LlmClient（简化版 - 用于编译通过）
 * TODO: D8 修复 langchain4j API 版本不匹配问题
 */
@Component
public class Langchain4jLlmClient implements LlmClient {

    private final ProviderConfig config;
    private final ProviderHealthRegistry healthRegistry;
    private final ObjectMapper objectMapper;

    public Langchain4jLlmClient(ProviderConfig config,
                                ProviderHealthRegistry healthRegistry,
                                ObjectMapper objectMapper) {
        this.config = config;
        this.healthRegistry = healthRegistry;
        this.objectMapper = objectMapper;
    }

    @Override
    public ChatResponse invoke(List<ChatMessage> messages) {
        ProviderId provider = resolveProvider();
        ChatLanguageModel model = createChatModel(provider);

        try {
            // TODO: 修复 API 调用
            return new ChatResponse("LLM 功能开发中...", List.of(), new dev.langchain4j.model.output.TokenUsage(0, 0, 0));
        } catch (Exception e) {
            healthRegistry.recordFailure(provider);
            throw e;
        }
    }

    @Override
    public ChatResponse invoke(List<ChatMessage> messages, List<ToolSpec> tools) {
        ProviderId provider = resolveProvider();
        ChatLanguageModel model = createChatModel(provider);

        try {
            // TODO: 修复工具调用
            return new ChatResponse("LLM 工具调用开发中...", List.of(), new dev.langchain4j.model.output.TokenUsage(0, 0, 0));
        } catch (Exception e) {
            healthRegistry.recordFailure(provider);
            throw e;
        }
    }

    @Override
    public void stream(List<ChatMessage> messages, StreamHandler handler) {
        stream(messages, List.of(), handler);
    }

    @Override
    public void stream(List<ChatMessage> messages, List<ToolSpec> tools, StreamHandler handler) {
        ProviderId provider = resolveProvider();
        try {
            handler.onPartialResponse("LLM 流式功能开发中...");
            handler.onComplete(new ChatResponse("LLM 流式功能开发中...", List.of(), new dev.langchain4j.model.output.TokenUsage(0, 0, 0)));
            healthRegistry.recordSuccess(provider);
        } catch (Exception e) {
            healthRegistry.recordFailure(provider);
            handler.onError(e);
        }
    }

    @Override
    public boolean isAvailable() {
        return healthRegistry.getHealthState(resolveProvider()) == HealthState.HEALTHY;
    }

    private ProviderId resolveProvider() {
        ProviderConfig.ProviderProperties primaryProps = config.getProviders().get(config.getPrimaryProvider());
        if (primaryProps != null && primaryProps.getApiKey() != null && !primaryProps.getApiKey().isEmpty()) {
            return ProviderId.from(config.getPrimaryProvider());
        }
        return ProviderId.DEEPSEEK;
    }

    private ChatLanguageModel createChatModel(ProviderId provider) {
        ProviderConfig.ProviderProperties props = config.getProviders().get(provider.getValue());
        if (props == null) {
            throw new IllegalStateException("Provider not configured: " + provider);
        }

        return OpenAiChatModel.builder()
            .apiKey(props.getApiKey())
            .baseUrl(props.getBaseUrl())
            .modelName(props.getModel())
            .temperature(0.7)
            .build();
    }

    private StreamingChatLanguageModel createStreamingChatModel(ProviderId provider) {
        ProviderConfig.ProviderProperties props = config.getProviders().get(provider.getValue());
        if (props == null) {
            throw new IllegalStateException("Provider not configured: " + provider);
        }

        return OpenAiStreamingChatModel.builder()
            .apiKey(props.getApiKey())
            .baseUrl(props.getBaseUrl())
            .modelName(props.getModel())
            .temperature(0.7)
            .build();
    }

    private ChatResponse toChatResponse(AiMessage aiMessage) {
        // TODO: D8 修复 langchain4j API
        return new ChatResponse(aiMessage.text(), List.of(), null);
    }
}
