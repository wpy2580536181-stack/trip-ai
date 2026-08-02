package com.trip.backend.service.agent.tools;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 美团酒旅 CLI 工具
 *
 * 对应 Python tools/meituan.py
 *
 * 功能：
 * - 调用美团酒旅官方 CLI 查询机票/酒店/火车票/景点门票
 * - ProcessBuilder spawn `npx @meituan-travel/ht-ai@latest query`
 * - 超时 150s
 * - MEITUAN_HT_TOKEN 环境变量校验
 * - 列表传参防注入
 */
public class MeituanTool {

    private static final Logger log = LoggerFactory.getLogger(MeituanTool.class);

    private static final String CMD = "npx";
    private static final String PKG = "@meituan-travel/ht-ai@latest";
    private static final String CHANNEL = "meituan-developer";
    private static final long TIMEOUT_MS = 150_000;

    // 控制字符清理
    private static final Pattern CONTROL_CHARS = Pattern.compile("[\\x00-\\x1f\\x7f]");

    /**
     * 执行工具调用
     *
     * @param query 用户自然语言查询
     * @param originQuery 用户原始完整输入（可选）
     * @param city 目标城市（可选）
     * @return 美团查询结果字符串
     */
    public String execute(String query, String originQuery, String city) {
        // 1. 校验 query
        if (query == null || query.isBlank()) {
            return "错误：查询内容为空。";
        }

        // 2. 校验环境变量
        String token = System.getenv("MEITUAN_HT_TOKEN");
        if (token == null || token.isBlank()) {
            return "未配置 MEITUAN_HT_TOKEN，无法调用美团酒旅接口。请在运行环境配置该环境变量后重试。";
        }

        // 3. 清理输入（防止控制字符）
        String safeQuery = sanitize(query);
        String safeOrigin = (originQuery != null && !originQuery.isBlank()) ? sanitize(originQuery) : safeQuery;
        String safeCity = (city != null && !city.isBlank()) ? sanitize(city) : "";

        // 4. 构建命令（列表传参，无 shell）
        ProcessBuilder pb = new ProcessBuilder(
            CMD, PKG, "query",
            "--query", safeQuery,
            "--origin-query", safeOrigin,
            "--channel", CHANNEL
        );
        if (!safeCity.isBlank()) {
            pb.command().addAll(List.of("--city", safeCity));
        }
        pb.redirectErrorStream(true);

        try {
            // 5. 启动进程
            Process process = pb.start();

            // 6. 异步读取输出（避免阻塞）
            StringBuilder output = new StringBuilder();
            Thread outputThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(new java.io.InputStreamReader(process.getInputStream()))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        output.append(line).append("\n");
                    }
                } catch (IOException e) {
                    log.warn("[MeituanTool] Failed to read output: {}", e.getMessage());
                }
            });
            outputThread.start();

            // 7. 等待进程完成（超时控制）
            boolean finished = process.waitFor(TIMEOUT_MS, java.util.concurrent.TimeUnit.MILLISECONDS);

            if (!finished) {
                process.destroy();
                outputThread.join(1000);
                return "美团酒旅接口请求超时（>150s），请稍后重试或更换问法。";
            }

            outputThread.join(1000);

            // 8. 处理返回码
            int exitCode = process.exitValue();
            String result = output.toString().trim();

            if (exitCode == 3) {
                return "美团鉴权失败（exit 3），请检查 MEITUAN_HT_TOKEN 是否正确配置。";
            }

            if (result.isBlank()) {
                return "美团未返回内容。";
            }

            return result;

        } catch (IOException e) {
            log.error("[MeituanTool] IOException: {}", e.getMessage(), e);
            return "美团酒旅查询失败：" + e.getMessage();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "美团酒旅查询被中断。";
        }
    }

    /**
     * 清理控制字符
     */
    private static String sanitize(String value) {
        if (value == null) {
            return "";
        }
        return CONTROL_CHARS.matcher(value).replaceAll(" ").trim();
    }

    // ==================== 工具定义 ====================

    public ToolSpecRegistry.ToolSpec getToolSpec() {
        return new ToolSpecRegistry.ToolSpec(
            "meituan_query",
            "调用美团酒旅官方 CLI 查询机票/酒店/火车票/景点门票。仅在用户明确需要美团官方酒旅数据（如「订酒店」「买机票」「门票」）时使用。",
            Map.of(
                "type", "object",
                "properties", Map.of(
                    "query", Map.of(
                        "type", "string",
                        "description", "用户的自然语言查询（必填）"
                    ),
                    "origin_query", Map.of(
                        "type", "string",
                        "description", "用户原始完整输入（可选）"
                    ),
                    "city", Map.of(
                        "type", "string",
                        "description", "目标城市（可选）"
                    )
                ),
                "required", List.of("query")
            )
        );
    }
}
