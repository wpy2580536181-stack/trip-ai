package com.trip.backend.service.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.chat.request.ChatRequest;
import dev.langchain4j.model.chat.request.json.JsonObjectSchema;
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
        return invokeAs(resolveProvider(), messages, tools);
    }

    /**
     * 按指定 ProviderId 调用（供 LlmGateway 在 fallback 时路由到备用 provider）。
     */
    public ChatResponse invokeAs(ProviderId provider, List<ChatMessage> messages, List<ToolSpec> tools) {
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

    List<dev.langchain4j.data.message.ChatMessage> toLangchainMessages(List<ChatMessage> messages) {
        List<dev.langchain4j.data.message.ChatMessage> result = new ArrayList<>();
        for (ChatMessage msg : messages) {
            switch (msg.role()) {
                case "system" -> result.add(SystemMessage.from(msg.content()));
                case "user" -> result.add(UserMessage.from(msg.content()));
                case "assistant" -> result.add(AiMessage.from(msg.content()));
                case "tool" -> {
                    // tool 角色消息：必须带 toolCallId，对应 assistant 发起的某一次 tool_call
                    if (msg.toolCallId() != null) {
                        result.add(new ToolExecutionResultMessage(
                            msg.toolCallId(),
                            msg.toolName() != null ? msg.toolName() : "unknown",
                            msg.content()));
                    } else {
                        // 兼容历史数据：缺 callId 的 tool 文本降级为 user 消息，避免整条消息丢失
                        result.add(UserMessage.from("[tool result] " + msg.content()));
                    }
                }
                default -> throw new IllegalArgumentException("Unknown message role: " + msg.role());
            }
        }
        return result;
    }

    ToolSpecification toToolSpecification(ToolSpec tool) {
        ToolSpecification.Builder builder = ToolSpecification.builder()
            .name(tool.name())
            .description(tool.description());

        // 把标准 JSON Schema 字符串转成 langchain4j 的 JsonObjectSchema；
        // 解析失败则降级为无参数 schema（不阻断请求）。
        JsonObjectSchema parameters = parseParametersSchema(tool.parametersSchema());
        if (parameters != null) {
            builder.parameters(parameters);
        }
        return builder.build();
    }

    /**
     * 解析 JSON Schema（{"type":"object","properties":{...},"required":[...]}）为 JsonObjectSchema。
     * 支持 string/integer/number/boolean 类型；未知类型按 string 兜底。
     */
    private JsonObjectSchema parseParametersSchema(String schemaJson) {
        if (schemaJson == null || schemaJson.isBlank()) {
            return null;
        }
        try {
            com.fasterxml.jackson.databind.JsonNode root = objectMapper.readTree(schemaJson);
            com.fasterxml.jackson.databind.JsonNode properties = root.get("properties");
            if (properties == null || !properties.isObject()) {
                return null;
            }
            JsonObjectSchema.Builder builder = JsonObjectSchema.builder();
            properties.fields().forEachRemaining(entry -> {
                String name = entry.getKey();
                com.fasterxml.jackson.databind.JsonNode prop = entry.getValue();
                String type = prop.path("type").asText("string");
                String desc = prop.has("description") ? prop.get("description").asText(null) : null;
                switch (type) {
                    case "integer" -> builder.addIntegerProperty(name, desc);
                    case "number" -> builder.addNumberProperty(name, desc);
                    case "boolean" -> builder.addBooleanProperty(name, desc);
                    default -> builder.addStringProperty(name, desc);
                }
            });
            com.fasterxml.jackson.databind.JsonNode required = root.get("required");
            if (required != null && required.isArray()) {
                List<String> requiredList = new ArrayList<>();
                required.forEach(n -> requiredList.add(n.asText()));
                builder.required(requiredList);
            }
            return builder.build();
        } catch (Exception e) {
            // 解析失败降级：不带 parameters，LLM 仍可收到 name+description
            return null;
        }
    }

    List<ToolCall> extractToolCalls(AiMessage aiMessage) {
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
