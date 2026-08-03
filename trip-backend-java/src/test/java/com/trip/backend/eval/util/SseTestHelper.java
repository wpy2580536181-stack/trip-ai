package com.trip.backend.eval.util;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * SSE 测试辅助工具
 */
public class SseTestHelper {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    /**
     * 测试 SSE 连接
     */
    public static void testSseConnection(String baseUrl, String token) {
        try {
            System.out.println("Testing SSE connection to: " + baseUrl + "/api/trip/recommend-stream");

            ProcessBuilder pb = new ProcessBuilder(
                "curl", "-s", "-X", "POST",
                baseUrl + "/api/trip/recommend-stream",
                "-H", "Content-Type: application/json",
                "-H", "Authorization: Bearer " + token,
                "-d", "{\"city\":\"北京\",\"days\":1,\"budget\":1000}"
            );

            Process process = pb.start();

            // 读取前 10 秒的输出
            long startTime = System.currentTimeMillis();
            long duration = 10000; // 10 秒

            BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream())
            );

            String line;
            int lineCount = 0;
            while ((line = reader.readLine()) != null &&
                   (System.currentTimeMillis() - startTime) < duration) {
                System.out.println("SSE [" + (++lineCount) + "]: " + line);
                Thread.sleep(100);
            }

            System.out.println("\nSSE test completed: " + lineCount + " events received in 10 seconds");
            process.destroy();

        } catch (Exception e) {
            System.err.println("SSE test failed: " + e.getMessage());
            e.printStackTrace();
        }
    }

    /**
     * 解析 SSE 事件
     */
    public static List<Map<String, Object>> parseSseEvents(String sseText) throws IOException {
        List<Map<String, Object>> events = new ArrayList<>();
        BufferedReader reader = new BufferedReader(new java.io.StringReader(sseText));

        String line;
        String eventType = "message";
        StringBuilder dataBuffer = new StringBuilder();

        while ((line = reader.readLine()) != null) {
            line = line.trim();

            if (line.isEmpty()) {
                if (dataBuffer.length() > 0) {
                    Map<String, Object> data = OBJECT_MAPPER.readValue(dataBuffer.toString(), Map.class);
                    events.add(Map.of("event", eventType, "data", data));
                    dataBuffer.setLength(0);
                }
                eventType = "message";
                continue;
            }

            if (line.startsWith("event:")) {
                eventType = line.substring(6).trim();
            } else if (line.startsWith("data:")) {
                String dataStr = line.substring(5).trim();
                if (dataBuffer.length() > 0) dataBuffer.append("\n");
                dataBuffer.append(dataStr);
            }
        }

        return events;
    }
}
