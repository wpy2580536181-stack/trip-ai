package com.trip.backend.eval.util;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * SSE (Server-Sent Events) 解析器
 * <p>
 * 解析 SSE 格式的流式响应：
 * <pre>
 * event: message
 * data: {"type": "chunk", "content": "..."}
 *
 * event: done
 * data: {"type": "complete"}
 * </pre>
 */
public class SseParser {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /**
     * SSE 事件
     */
    public record SseEvent(String event, Map<String, Object> data) {
    }

    /**
     * 解析 SSE 文本流
     *
     * @param sseText SSE 原始文本
     * @return 事件列表
     * @throws IOException 如果 JSON 解析失败
     */
    public static List<SseEvent> parse(String sseText) throws IOException {
        List<SseEvent> events = new ArrayList<>();
        BufferedReader reader = new BufferedReader(new StringReader(sseText));

        String line;
        String currentEvent = "message";  // 默认事件类型
        StringBuilder dataBuffer = new StringBuilder();

        try {
            while ((line = reader.readLine()) != null) {
                line = line.trim();

                // 空行表示一个事件的结束
                if (line.isEmpty()) {
                    if (dataBuffer.length() > 0) {
                        Map<String, Object> data = OBJECT_MAPPER.readValue(dataBuffer.toString(), Map.class);
                        events.add(new SseEvent(currentEvent, data));
                        dataBuffer.setLength(0);
                    }
                    currentEvent = "message";  // 重置为默认
                    continue;
                }

                // 解析 event: 行
                if (line.startsWith("event:")) {
                    currentEvent = line.substring(6).trim();
                    continue;
                }

                // 解析 data: 行
                if (line.startsWith("data:")) {
                    String dataStr = line.substring(5).trim();
                    if (dataBuffer.length() > 0) {
                        dataBuffer.append("\n");
                    }
                    dataBuffer.append(dataStr);
                    continue;
                }

                // 忽略其他字段（id:, retry: 等）
            }

            // 处理最后一个事件（如果没有以空行结束）
            if (dataBuffer.length() > 0) {
                Map<String, Object> data = OBJECT_MAPPER.readValue(dataBuffer.toString(), Map.class);
                events.add(new SseEvent(currentEvent, data));
            }

        } catch (IOException e) {
            throw new IOException("Failed to parse SSE: " + e.getMessage(), e);
        }

        return events;
    }

    /**
     * 从 SSE 事件中提取最终 JSON 结果
     *
     * @param events SSE 事件列表
     * @return 最终的 JSON 对象
     */
    public static Map<String, Object> extractFinalResult(List<SseEvent> events) {
        // 查找最后一个 "done" 或 "complete" 事件
        for (int i = events.size() - 1; i >= 0; i--) {
            SseEvent event = events.get(i);
            if ("done".equals(event.event) || "complete".equals(event.event)) {
                return event.data;
            }
        }

        // 如果没有 done 事件，返回最后一个 message 事件的数据
        if (!events.isEmpty()) {
            return events.get(events.size() - 1).data;
        }

        return null;
    }

    /**
     * 从 SSE 事件中提取累积文本
     *
     * @param events SSE 事件列表
     * @return 累积的文本内容
     */
    public static String extractAccumulatedText(List<SseEvent> events) {
        StringBuilder text = new StringBuilder();
        for (SseEvent event : events) {
            if ("message".equals(event.event) && event.data.containsKey("content")) {
                Object content = event.data.get("content");
                if (content != null) {
                    text.append(content.toString());
                }
            }
        }
        return text.toString();
    }
}
