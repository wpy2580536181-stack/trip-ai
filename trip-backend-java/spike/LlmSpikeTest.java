package com.trip.backend.spike;

import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import dev.langchain4j.service.AiServices;
import dev.langchain4j.service.UserMessage;
import dev.langchain4j.service.V;
import dev.langchain4j.model.output.TokenUsage;
import dev.langchain4j.data.message.*;
import dev.langchain4j.data.audio.AudioContent;
import dev.langchain4j.data.image.ImageContent;
import dev.langchain4j.data.json.JsonElement;
import dev.langchain4j.agent.tool.Tool;
import dev.langchain4j.agent.tool.P;
import dev.langchain4j.agent.tool.ToolSpecification;
import dev.langchain4j.agent.tool.ToolSpecifications;
import dev.langchain4j.agent.tool.ToolExecutor;
import dev.langchain4j.agent.tool.DefaultToolExecutor;
import java.util.List;

import static dev.langchain4j.data.message.UserMessage.from;

/**
 * LLM Spike Test - 验证 langchain4j 1.x 关键能力
 *
 * 测试目标：
 * 1. 流式 tool_calls delta 累积（能否逐步累积完整工具调用）
 * 2. 末帧 usage 提取（include_usage + cachedTokens）
 * 3. 中文 tool schema（description 字段）
 */
public class LlmSpikeTest {

    private static final String DEEPSEEK_API_KEY = System.getenv().getOrDefault("DEEPSEEK_API_KEY", "");
    private static final String DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1";
    private static final String DEEPSEEK_MODEL = "deepseek-chat";

    public static void main(String[] args) {
        System.out.println("=".repeat(60));
        System.out.println("LLM Spike Test - langchain4j 1.x");
        System.out.println("=".repeat(60));

        // 检查 API Key
        if (DEEPSEEK_API_KEY.isEmpty()) {
            System.err.println("❌ DEEPSEEK_API_KEY 环境变量未设置");
            System.exit(1);
        }

        try {
            // 测试 1: 非流式调用（验证基础能力）
            System.out.println("\n[测试 1] 非流式调用 + 工具定义");
            testSyncWithTools();

            // 测试 2: 流式调用 + tool_calls delta 累积
            System.out.println("\n[测试 2] 流式调用 + tool_calls delta 累积");
            testStreamingToolCalls();

            // 测试 3: usage 提取（含 cachedTokens）
            System.out.println("\n[测试 3] usage 提取（含 cachedTokens）");
            testUsageExtraction();

            // 测试 4: 中文 tool schema
            System.out.println("\n[测试 4] 中文 tool schema 下发");
            testChineseToolSchema();

            System.out.println("\n" + "=".repeat(60));
            System.out.println("✅ 所有测试完成");
            System.out.println("=".repeat(60));

        } catch (Exception e) {
            System.err.println("\n❌ 测试失败: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }
    }

    /**
     * 测试 1: 非流式调用 + 工具定义
     */
    private static void testSyncWithTools() {
        ChatLanguageModel model = OpenAiChatModel.builder()
            .apiKey(DEEPSEEK_API_KEY)
            .baseUrl(DEEPSEEK_BASE_URL)
            .modelName(DEEPSEEK_MODEL)
            .temperature(0.7)
            .build();

        // 定义工具（测试中文 description）
        ToolSpecification weatherTool = ToolSpecification.builder()
            .name("get_weather")
            .description("获取指定城市的天气信息")
            .addParameter("city", JsonElement.from("{\"type\": \"string\", \"description\": \"城市名称\"}"))
            .build();

        // 构建请求
        UserMessage message = UserMessage.from("北京今天天气怎么样？请调用 get_weather 工具");

        // 调用
        var response = model.chat(message, List.of(weatherTool));

        System.out.println("回复: " + response.aiMessage().text());
        System.out.println("Token 使用: " + response.tokenUsage());

        if (response.aiMessage().toolCalls() != null && !response.aiMessage().toolCalls().isEmpty()) {
            System.out.println("✅ 工具调用成功: " + response.aiMessage().toolCalls().size() + " 个");
        } else {
            System.out.println("⚠️ 未触发工具调用（可能是模型未选择调用工具）");
        }
    }

    /**
     * 测试 2: 流式调用 + tool_calls delta 累积
     *
     * 核心验证点：
     * - 流式过程中能否逐步累积 tool_calls delta
     * - 最终能否还原出完整工具调用
     */
    private static void testStreamingToolCalls() {
        StreamingChatLanguageModel model = OpenAiStreamingChatModel.builder()
            .apiKey(DEEPSEEK_API_KEY)
            .baseUrl(DEEPSEEK_BASE_URL)
            .modelName(DEEPSEEK_MODEL)
            .temperature(0.7)
            .build();

        ToolSpecification searchTool = ToolSpecification.builder()
            .name("search_spots")
            .description("搜索景点信息")
            .addParameter("query", JsonElement.from("{\"type\": \"string\", \"description\": \"搜索关键词\"}"))
            .addParameter("city", JsonElement.from("{\"type\": \"string\", \"description\": \"城市名称，可选\"}"))
            .build();

        UserMessage message = UserMessage.from("帮我搜索北京的热门景点");

        // 流式处理
        StringBuilder textBuffer = new StringBuilder();
        StringBuilder toolCallsBuffer = new StringBuilder();

        model.chat(List.of(message), List.of(searchTool), new StreamingChatResponseHandler() {
            @Override
            public void onPartialResponse(String partialResponse) {
                textBuffer.append(partialResponse);
            }

            @Override
            public void onToolCall(String toolCallJson) {
                toolCallsBuffer.append(toolCallJson);
            }

            @Override
            public void onComplete(TokenUsage tokenUsage) {
                System.out.println("完整文本: " + textBuffer);
                System.out.println("Tool Calls JSON: " + toolCallsBuffer);
                System.out.println("Token 使用: " + tokenUsage);

                if (toolCallsBuffer.length() > 0) {
                    System.out.println("✅ 流式 tool_calls 累积成功（长度=" + toolCallsBuffer.length() + "）");
                } else {
                    System.out.println("⚠️ 流式过程中未收到 tool_calls delta");
                }
            }

            @Override
            public void onError(Throwable error) {
                System.err.println("❌ 流式调用失败: " + error.getMessage());
            }
        });
    }

    /**
     * 测试 3: usage 提取（含 cachedTokens）
     *
     * 核心验证点：
     * - 能否提取 prompt/completion/total
     * - 能否提取 cachedTokens（prompt_cache_hit_tokens）
     */
    private static void testUsageExtraction() {
        ChatLanguageModel model = OpenAiChatModel.builder()
            .apiKey(DEEPSEEK_API_KEY)
            .baseUrl(DEEPSEEK_BASE_URL)
            .modelName(DEEPSEEK_MODEL)
            .build();

        UserMessage message = UserMessage.from("你好");

        var response = model.chat(message);

        TokenUsage tokenUsage = response.tokenUsage();
        System.out.println("Token 使用详情:");
        System.out.println("  inputTokens: " + tokenUsage.inputTokenCount());
        System.out.println("  outputTokens: " + tokenUsage.outputTokenCount());
        System.out.println("  totalTokens: " + tokenUsage.totalTokenCount());

        // 检查 cachedTokens
        try {
            // 尝试通过 reflection 或扩展字段获取 cachedTokens
            Object cachedTokens = tokenUsage.additionalProperties().get("prompt_cache_hit_tokens");
            if (cachedTokens != null) {
                System.out.println("  cachedTokens: " + cachedTokens);
                System.out.println("✅ cachedTokens 提取成功");
            } else {
                System.out.println("⚠️ cachedTokens 字段不存在（可能需要检查 API 响应格式）");
            }
        } catch (Exception e) {
            System.out.println("⚠️ 无法提取 cachedTokens: " + e.getMessage());
        }

        if (tokenUsage.totalTokenCount() > 0) {
            System.out.println("✅ Token 使用统计正常");
        }
    }

    /**
     * 测试 4: 中文 tool schema 下发
     *
     * 核心验证点：
     * - description 字段中文是否正常下发
     * - parameter 描述是否正常
     */
    private static void testChineseToolSchema() {
        ChatLanguageModel model = OpenAiChatModel.builder()
            .apiKey(DEEPSEEK_API_KEY)
            .baseUrl(DEEPSEEK_BASE_URL)
            .modelName(DEEPSEEK_MODEL)
            .build();

        // 定义中文工具
        ToolSpecification poiTool = ToolSpecification.builder()
            .name("search_poi")
            .description("搜索附近的餐厅、景点、酒店等兴趣点")
            .addParameter("query", JsonElement.from("{\"type\": \"string\", \"description\": \"搜索关键词，如\"火锅\"、\"故宫\"}"))
            .addParameter("city", JsonElement.from("{\"type\": \"string\", \"description\": \"所在城市，如\"北京\"、\"上海\"}"))
            .addParameter("radius", JsonElement.from("{\"type\": \"integer\", \"description\": \"搜索半径（米），默认 1000\"}"))
            .build();

        UserMessage message = UserMessage.from("请帮我调用 search_poi 工具搜索北京的故宫");

        var response = model.chat(message, List.of(poiTool));

        System.out.println("回复: " + response.aiMessage().text());

        // 检查 tool_calls
        if (response.aiMessage().toolCalls() != null && !response.aiMessage().toolCalls().isEmpty()) {
            var toolCall = response.aiMessage().toolCalls().get(0);
            System.out.println("工具名称: " + toolCall.name());
            System.out.println("参数: " + toolCall.arguments());
            System.out.println("✅ 中文 tool schema 调用成功");
        } else {
            System.out.println("⚠️ 未触发工具调用");
        }
    }

    // ========== 辅助接口 ==========

    interface StreamingChatResponseHandler {
        void onPartialResponse(String partialResponse);
        void onToolCall(String toolCallJson);
        void onComplete(TokenUsage tokenUsage);
        void onError(Throwable error);
    }
}
