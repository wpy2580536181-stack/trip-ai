package com.trip.backend.service.agent.tools;

import com.trip.backend.service.llm.LlmClient;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * meituan_query 工具（对应 Python tools/meituan.py）。
 * 沙箱化执行 `npx @meituan-travel/ht-ai@latest query`，列表式传参杜绝命令注入。
 * 未配置 MEITUAN_HT_TOKEN / 无 npx / 超时均返回明确文案，不抛异常。
 */
@Component
public class MeituanTool implements AgentTool {

    private static final Pattern CONTROL_CHARS = Pattern.compile("[\\x00-\\x1f\\x7f]");
    private static final long TIMEOUT_SEC = 150;

    @Override
    public String name() {
        return "meituan_query";
    }

    @Override
    public String description() {
        return """
            调用美团酒旅官方 CLI 查询机票/酒店/火车票/景点门票。

            仅在用户明确需要美团官方酒旅数据（如「订酒店」「买机票」「门票」）时使用。
            query 为用户自然语言查询；city 为目标城市（可选）。""";
    }

    @Override
    public LlmClient.ToolSpec spec() {
        return new LlmClient.ToolSpec(name(), description(),
            """
            {"type":"object",
             "properties":{
               "query":{"type":"string","description":"用户的自然语言查询（必填）"},
               "origin_query":{"type":"string","description":"用户原始完整输入（用于统计，缺省同 query）"},
               "city":{"type":"string","description":"城市名称（可选）"}
             },
             "required":["query"]}""");
    }

    @Override
    public String execute(Map<String, Object> args) throws Exception {
        String query = sanitize(args.get("query") == null ? "" : args.get("query").toString());
        if (query.isEmpty()) {
            return "错误：查询内容为空。";
        }
        String origin = sanitize(args.get("origin_query") == null ? "" : args.get("origin_query").toString());
        if (origin.isEmpty()) {
            origin = query;
        }
        String city = sanitize(args.get("city") == null ? "" : args.get("city").toString());

        String token = System.getenv("MEITUAN_HT_TOKEN");
        if (token == null || token.isBlank()) {
            return "未配置 MEITUAN_HT_TOKEN，无法调用美团酒旅接口。请在运行环境配置该环境变量后重试。";
        }

        ProcessBuilder pb = new ProcessBuilder(
            "npx", "@meituan-travel/ht-ai@latest", "query",
            "--query", query,
            "--origin-query", origin,
            "--channel", "meituan-developer"
        );
        if (!city.isEmpty()) {
            pb.command().add("--city");
            pb.command().add(city);
        }
        pb.redirectErrorStream(false);

        Process proc;
        try {
            proc = pb.start();
        } catch (Exception e) {
            return "未找到 npx，无法执行美团酒旅 CLI。请确认运行环境已安装 Node.js 与 npx。";
        }

        if (!proc.waitFor(TIMEOUT_SEC, java.util.concurrent.TimeUnit.SECONDS)) {
            proc.destroyForcibly();
            return "美团酒旅接口请求超时（>150s），请稍后重试或更换问法。";
        }

        String out = readAll(proc);
        int code = proc.exitValue();
        if (code == 3) {
            return "美团鉴权失败（exit 3），请检查 MEITUAN_HT_TOKEN 是否正确配置。";
        }
        if (out.isBlank()) {
            return "美团未返回内容。";
        }
        return out;
    }

    @Override
    public String fallback() {
        return "美团酒旅查询暂时不可用。";
    }

    @Override
    public long timeoutSec() {
        return TIMEOUT_SEC;
    }

    @Override
    public int retries() {
        return 0;
    }

    private static String sanitize(String v) {
        if (v == null || v.isEmpty()) {
            return "";
        }
        return CONTROL_CHARS.matcher(v).replaceAll(" ").trim();
    }

    private static String readAll(Process proc) throws Exception {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader r = new BufferedReader(
            new InputStreamReader(proc.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = r.readLine()) != null) {
                sb.append(line).append('\n');
            }
        }
        return sb.toString().trim();
    }
}
