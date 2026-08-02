package com.trip.backend.service.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import dev.langchain4j.data.message.*;
import dev.langchain4j.data.json.JsonElement;
import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.agent.tool.ToolSpecifications;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * langchain4j 实现的 LlmClient（对应 Python config/llm.py）
 * - OpenAI 兼容协议（DeepSeek/Kimi/Agnes 通用）
 * - 流式 + 非流式
 * - 工具调用
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
        var model = createChatModel(provider);

        try {
            var response = model.chat(messages);
            return toChatResponse(response);
        } catch (Exception e) {
            healthRegistry.recordFailure(provider);
            throw e;
        }
    }

    @Override
    public ChatResponse invoke(List<ChatMessage> messages, List<ToolSpec> tools) {
        ProviderId provider = resolveProvider();
        var model = createChatModel(provider);

        try {
            // 转换工具规格
            List<ToolSpecification> toolSpecs = tools.stream()
                .map(t -> ToolSpecification.builder()
                    .name(t.name())
                    .description(t.description())
                    .addParameter("parameters", JsonElement.from(t.parametersSchema()))
                    .build())
                .toList();

            var response = model.chat(messages, toolSpecs);
            return toChatResponse(response);
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
        var model = createStreamingChatModel(provider);

        try {
            List<ToolSpecification> toolSpecs = tools.stream()
                .map(t -> ToolSpecification.builder()
                    .name(t.name())
                    .description(t.description())
                    .addParameter("parameters", JsonElement.from(t.parametersSchema()))
                    .build())
                .toList();

            model.chat(messages, toolSpecs, new dev.langchain4j.model.chat.StreamingChatResponseHandler() {
                @Override
                public void onPartialResponse(String partialResponse) {
                    handler.onPartialResponse(partialResponse);
                }

                @Override
                public void onComplete(dev.langchain4j.model.output.TokenUsage tokenUsage) {
                    handler.onComplete(new ChatResponse("", List.of(), tokenUsage));
                }

                @Override
                public void onError(Throwable error) {
                    handler.onError(error);
                }
            });

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
        return ProviderId.DEEPSEEK; // 默认
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

    private ChatResponse toChatResponse(dev.langchain4j.data.message.AiMessage aiMessage) {
        List<ToolCall> toolCalls = List.of();
        if (aiMessage.toolCalls() != null && !aiMessage.toolCalls().isEmpty()) {
            toolCalls = aiMessage.toolCalls().stream()
                .map(tc -> new ToolCall(tc.name(), tc.arguments().toJson()))
                .toList();
        }

        return new ChatResponse(
            aiMessage.text(),
            toolCalls,
            null // TODO: 提取 token usage
        );
    }
}
