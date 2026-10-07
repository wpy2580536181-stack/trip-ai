package com.trip.backend.service.agent;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.domain.entity.Message;
import com.trip.backend.domain.skill.SkillContext;
import com.trip.backend.domain.skill.SkillResult;
import com.trip.backend.infra.skill.SkillRegistry;
import com.trip.backend.infra.skill.patch.PatchEngine;
import com.trip.backend.infra.skill.patch.PatchError;
import com.trip.backend.middleware.TokenTrackingCallback;
import com.trip.backend.service.agent.tools.ToolSpecRegistry;
import com.trip.backend.service.chat.EventSink;
import com.trip.backend.service.llm.LlmClient;
import com.trip.backend.service.llm.LlmGateway;
import com.trip.backend.service.llm.Scenario;
import com.trip.backend.web.sse.SseWriter;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * ChatAgent：对话 Agent（职责：LLM 流式调用 + ReAct 多轮工具编排 + 技能执行）
 *
 * 对应 Python: chat_agent.py (ChatAgent)
 *
 * 核心职责：
 * - chatStream()：LLM 流式 + 多轮工具调用循环（MAX_TURNS=5）
 * - 逐 chunk 推送 SSE，累积完整回复文本
 * - Token 累积 + 预算检查 + 异步落库
 * - runSelectedSkill()：检测 select_skill 并执行技能
 * - applyPatch()：槽位级修改
 */
@Component
public class ChatAgent {

    private static final String CHAT_SYSTEM_PROMPT =
        "你是一个专业的旅行规划助手。需要景点、酒店、距离等实时信息时，请调用提供的工具检索，"
        + "不要凭空编造。拿到工具结果后，再用自然语言为用户给出完整、有条理的回答。"
        + "当用户请你推荐目的地时，请使用“推荐”“建议”等表述，并原样保留用户提到的时间（如“6月”）等关键信息；"
        + "若需要候选目的地的资料，应调用 retrieve_knowledge 工具检索后再回答。"
        + "请区分请求类型：仅当用户明确要求完整行程规划时，才输出按天（Day 1/Day 2 或第1天/第2天）的行程；"
        + "若用户仍在选择目的地（如“还没决定去哪、先推荐几个地方”）或追问已规划景点的详情（如码头、票价），"
        + "必须先调用 retrieve_knowledge 检索（至少1次），再用连贯自然语言回答，不要出现 Day 1/Day 2 式行程，"
        + "并保留用户提到的时间（如“6月”）等关键词。";

    private final LlmGateway llmGateway;
    private final ToolSpecRegistry toolSpecRegistry;
    private final EventSink eventSink;
    private final TokenTrackingCallback tokenTrackingCallback;
    private final SkillRegistry skillRegistry;
    private final PatchEngine patchEngine;

    private final ObjectMapper objectMapper = new ObjectMapper();

    public ChatAgent(LlmGateway llmGateway,
                     ToolSpecRegistry toolSpecRegistry,
                     EventSink eventSink,
                     TokenTrackingCallback tokenTrackingCallback,
                     SkillRegistry skillRegistry,
                     PatchEngine patchEngine) {
        this.llmGateway = llmGateway;
        this.toolSpecRegistry = toolSpecRegistry;
        this.eventSink = eventSink;
        this.tokenTrackingCallback = tokenTrackingCallback;
        this.skillRegistry = skillRegistry;
        this.patchEngine = patchEngine;
    }

    /**
     * 流式对话：ReAct 多轮工具循环
     *
     * 逐 chunk 推送 SSE，累积完整回复文本和 token 用量。
     * 循环结束后执行 token 记账（预算检查 + 异步落库）。
     *
     * @param sseWriter   SSE 写入器
     * @param streamId    流 ID
     * @param userId      用户 ID
     * @param userMessage 用户消息
     * @param historyMsgs 历史消息
     * @return ChatResult（完整回复文本 + 执行的工具名 + token 用量 + 是否预算超限）
     */
    public ChatResult chatStream(SseWriter sseWriter, String streamId, Long userId,
                                  String userMessage, List<Message> historyMsgs) {
        StringBuilder fullText = new StringBuilder();
        List<LlmClient.ChatMessage> convo = new ArrayList<>();
        convo.add(LlmClient.ChatMessage.of("system", CHAT_SYSTEM_PROMPT));
        for (Message hm : historyMsgs) {
            if (hm.getContent() == null || hm.getContent().isBlank()) continue;
            convo.add(LlmClient.ChatMessage.of(hm.getRole(), hm.getContent()));
        }
        convo.add(LlmClient.ChatMessage.of("user", userMessage));
        List<LlmClient.ToolSpec> specs = toolSpecRegistry.toolSpecs();
        List<String> executedToolNames = new ArrayList<>();

        // Token 累积（多轮 ReAct 循环）
        final int[] tokenAccum = {0, 0, 0}; // [prompt, completion, total]
        final long llmStartMs = System.currentTimeMillis();

        final int MAX_TURNS = 5;
        for (int turn = 0; turn < MAX_TURNS; turn++) {
            final CountDownLatch latch = new CountDownLatch(1);
            final List<LlmClient.ToolCall>[] toolCallsHolder = new List[]{List.of()};
            final Throwable[] errHolder = new Throwable[]{null};
            final StringBuilder turnText = new StringBuilder();

            llmGateway.stream(Scenario.CHAT, convo, specs, new LlmClient.StreamHandler() {
                @Override public void onPartialResponse(String text) {
                    turnText.append(text);
                    fullText.append(text);
                    eventSink.sendChunk(sseWriter, streamId, text);
                }
                @Override public void onToolCallDelta(String json) { /* 流式工具增量暂不处理 */ }
                @Override public void onComplete(LlmClient.ChatResponse response) {
                    if (response != null && response.toolCalls() != null) {
                        toolCallsHolder[0] = response.toolCalls();
                    }
                    if (response != null && response.tokenUsage() != null) {
                        dev.langchain4j.model.output.TokenUsage tu = response.tokenUsage();
                        tokenAccum[0] += tu.inputTokenCount() != null ? tu.inputTokenCount() : 0;
                        tokenAccum[1] += tu.outputTokenCount() != null ? tu.outputTokenCount() : 0;
                        tokenAccum[2] += tu.totalTokenCount() != null ? tu.totalTokenCount() : 0;
                    }
                    latch.countDown();
                }
                @Override public void onError(Throwable error) {
                    errHolder[0] = error;
                    latch.countDown();
                }
            });
            try {
                latch.await(120, TimeUnit.SECONDS);
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            }

            if (errHolder[0] != null) {
                Throwable e = errHolder[0];
                System.err.println("[CHAT-LLM-ERROR] turn=" + turn + " : " + e);
                String note = "（LLM 调用失败：" + e.getMessage() + "）";
                fullText.append(note);
                eventSink.sendChunk(sseWriter, streamId, note);
                break;
            }

            List<LlmClient.ToolCall> calls = toolCallsHolder[0];
            if (calls.isEmpty()) {
                // 无工具调用：最终自然语言回复已通过 onPartialResponse 逐字推送
                break;
            }

            // 有工具调用：记录 assistant 这一轮，逐个执行工具并把结果回灌
            if (!turnText.isEmpty()) {
                convo.add(LlmClient.ChatMessage.of("assistant", turnText.toString()));
            }
            for (LlmClient.ToolCall call : calls) {
                executedToolNames.add(call.name());
                System.out.println("[CHAT-TOOL] turn=" + turn + " call=" + call.name()
                    + " args=" + call.arguments());
                Map<String, Object> args = parseToolArgs(call.arguments());
                String result;
                try {
                    result = toolSpecRegistry.call(call.name(), args);
                } catch (Exception ex) {
                    result = "工具执行失败: " + ex.getMessage();
                }
                System.out.println("[CHAT-TOOL] result(head)="
                    + (result != null ? result.substring(0, Math.min(120, result.length())) : "null"));
                // 用 user 消息回灌工具结果（避免 tool_call/tool result 严格配对问题）
                convo.add(LlmClient.ChatMessage.of("user",
                    "[工具结果] 调用 " + call.name() + " 返回：\n" + result));
            }
        }

        // Token 记账：预算检查 + 异步落库 token_usage_logs
        boolean budgetExceeded = false;
        try {
            tokenTrackingCallback.setContext(userId, "chat", "/api/trip/chat");
            tokenTrackingCallback.recordLlmUsage(
                new dev.langchain4j.model.output.TokenUsage(tokenAccum[0], tokenAccum[1], tokenAccum[2]),
                System.currentTimeMillis() - llmStartMs
            );
        } catch (TokenTrackingCallback.TokenBudgetExceededException be) {
            eventSink.sendError(sseWriter, streamId, "Token budget exceeded");
            budgetExceeded = true;
        } finally {
            tokenTrackingCallback.clearContext();
        }

        return new ChatResult(fullText.toString(), executedToolNames,
            tokenAccum[0], tokenAccum[1], tokenAccum[2], budgetExceeded);
    }

    /**
     * 执行选中的技能
     *
     * 对应 Python: _run_selected_skill()
     */
    public SkillResult runSelectedSkill(String userInput, String skillName, Map<String, Object> kwargs) {
        if (skillRegistry == null || skillName == null) {
            return SkillResult.failure(skillName, "SkillRegistry 未注入或技能名为空");
        }

        SkillContext ctx = new SkillContext(
            llmGateway,
            new ArrayList<>(),
            skillRegistry,
            userInput,
            new ArrayList<>()
        );

        return skillRegistry.execute(skillName, ctx, kwargs);
    }

    /**
     * 应用 patch（修改行程）
     */
    public JsonNode applyPatch(JsonNode trip, String op, int day, PatchEngine.PatchParams params) throws PatchError {
        return patchEngine.applyPatch(trip, op, day, params);
    }

    /** 解析工具 arguments JSON 字符串为 Map；失败返回空 Map。 */
    private Map<String, Object> parseToolArgs(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (Exception e) {
            return Map.of();
        }
    }

    /**
     * ChatAgent 流式对话结果
     */
    public record ChatResult(
        String fullText,
        List<String> executedToolNames,
        int promptTokens,
        int completionTokens,
        int totalTokens,
        boolean budgetExceeded
    ) {}
}
