package com.trip.backend.service.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.response.StreamingChatResponseHandler;
import dev.langchain4j.model.output.TokenUsage;
import dev.langchain4j.data.message.*;
import dev.langchain4j.agent.tool.ToolExecutionRequest;
import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

/**
 * langchain4j 实现的 LlmClient（D8 真实调用版本）
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
        return invoke(messages, List.of());
    }

    @Override
    public ChatResponse invoke(List<ChatMessage> messages, List<ToolSpec> tools) {
        ProviderId provider = resolveProvider();
        ChatLanguageModel model = createChatModel(provider);

        try {
            List<dev.langchain4j.data.message.ChatMessage> langchainMessages = toLangchainMessages(messages);
            
            ChatRequest.Builder requestBuilder = ChatRequest.builder()
                .messages(langchainMessages);
            
            if (!tools.isEmpty()) {
                List<ToolSpecification> toolSpecs = tools.stream()
                    .map(this::toToolSpecification)
                    .toList();
                requestBuilder.toolSpecifications(toolSpecs);
            }
            
            ChatRequest request = requestBuilder.build();
            dev.langchain4j.model.chat.response.ChatResponse response = model.chat(request);
            
            AiMessage aiMessage = response.aiMessage();
            TokenUsage tokenUsage = response.tokenUsage();
            List<ToolCall> toolCalls = extractToolCalls(aiMessage);

            return new ChatResponse(aiMessage.text(), toolCalls, tokenUsage);

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
        StreamingChatLanguageModel model = createStreamingChatModel(provider);

        try {
            List<dev.langchain4j.data.message.ChatMessage> langchainMessages = toLangchainMessages(messages);
            
            ChatRequest.Builder requestBuilder = ChatRequest.builder()
                .messages(langchainMessages);
            
            if (!tools.isEmpty()) {
                List<ToolSpecification> toolSpecs = tools.stream()
                    .map(this::toToolSpecification)
                    .toList();
                requestBuilder.toolSpecifications(toolSpecs);
            }
            
            ChatRequest request = requestBuilder.build();

            model.chat(request, new StreamingChatResponseHandler() {
                @Override
                public void onPartialResponse(String partialResponse) {
                    handler.onPartialResponse(partialResponse);
                }

                @Override
                public void onCompleteResponse(dev.langchain4j.model.chat.response.ChatResponse response) {
                    AiMessage aiMessage = response.aiMessage();
                    TokenUsage tokenUsage = response.tokenUsage();
                    List<ToolCall> toolCalls = extractToolCalls(aiMessage);
                    handler.onComplete(new ChatResponse(aiMessage.text(), toolCalls, tokenUsage));
                }

                @Override
                public void onError(Throwable throwable) {
                    handler.onError(throwable);
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
        return ProviderId.DEEPSEEK;
    }

    private ChatLanguageModel createChatModel(ProviderId provider) {
        ProviderConfig.ProviderProperties props = config.getProviders().get(provider.getValue());
        if (props == null || props.getApiKey() == null || props.getApiKey().isEmpty()) {
            throw new IllegalStateException("Provider not configured or missing API key: " + provider);
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
        if (props == null || props.getApiKey() == null || props.getApiKey().isEmpty()) {
            throw new IllegalStateException("Provider not configured or missing API key: " + provider);
        }

        return OpenAiStreamingChatModel.builder()
            .apiKey(props.getApiKey())
            .baseUrl(props.getBaseUrl())
            .modelName(props.getModel())
            .temperature(0.7)
            .build();
    }

    private List<dev.langchain4j.data.message.ChatMessage> toLangchainMessages(List<ChatMessage> messages) {
        List<dev.langchain4j.data.message.ChatMessage> result = new ArrayList<>();
        for (ChatMessage msg : messages) {
            switch (msg.role()) {
                case "system" -> result.add(SystemMessage.from(msg.content()));
                case "user" -> result.add(UserMessage.from(msg.content()));
                case "assistant" -> result.add(AiMessage.from(msg.content()));
                case "tool" -> { // TODO: D8 支持 tool 角色消息
                    // result.add(ToolExecutionResultMessage.from(msg.content()));
                }
                default -> throw new IllegalArgumentException("Unknown message role: " + msg.role());
            }
        }
        return result;
    }

    private ToolSpecification toToolSpecification(ToolSpec tool) {
        // TODO: D8 完善工具参数解析
        return ToolSpecification.builder()
            .name(tool.name())
            .description(tool.description())
            .build();
    }

    private List<ToolCall> extractToolCalls(AiMessage aiMessage) {
        List<ToolCall> result = new ArrayList<>();

        if (aiMessage.hasToolExecutionRequests() && aiMessage.toolExecutionRequests() != null) {
            for (ToolExecutionRequest tc : aiMessage.toolExecutionRequests()) {
                result.add(new ToolCall(
                    tc.name(),
                    tc.arguments() != null ? tc.arguments() : "{}"
                ));
            }
        }

        return result;
    }
}
