package com.trip.backend.service.alert;

import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Webhook 告警通知（对应 Python alert_webhook.py）。
 *
 * <p>formatPayload 为纯函数，返回各平台消息体结构；HTTP 发送由调用方按需注入。
 * 支持 feishu / slack / dingtalk / wecom / custom 五种。
 */
@Component
public class AlertWebhook {

    private static final String TITLE = "⚠️ Feedback 满意率告警";

    /** 构造 5 种平台 payload。 */
    public Map<String, Object> formatPayload(String webhookType, AlertCheckResult check, String dashboardUrl) {
        String summary = check.reason();
        String link = dashboardUrl + "/admin/feedback";

        List<String> commentLines = new ArrayList<>();
        for (Map<String, Object> c : check.recentDownComments()) {
            String comment = String.valueOf(c.getOrDefault("comment", ""));
            Object tags = c.get("tags");
            String tagStr = "";
            if (tags instanceof List<?> list && !list.isEmpty()) {
                tagStr = " [" + String.join(", ", list.stream().map(String::valueOf).toList()) + "]";
            }
            commentLines.add("- " + comment + tagStr);
        }
        String comments = commentLines.isEmpty() ? "（无评论）" : String.join("\n", commentLines);

        return switch (webhookType == null ? "custom" : webhookType) {
            case "feishu" -> {
                Map<String, Object> card = new LinkedHashMap<>();
                card.put("header", Map.of("title", Map.of("tag", "plain_text", "content", TITLE)));
                List<Map<String, Object>> elements = new ArrayList<>();
                elements.add(Map.of("tag", "div", "text",
                        Map.of("tag", "lark_md", "content", "**" + summary + "**\n\n最近差评：\n" + comments)));
                elements.add(Map.of("tag", "action", "actions", List.of(Map.of(
                        "tag", "button", "text", Map.of("tag", "plain_text", "content", "查看 Dashboard"),
                        "type", "primary", "url", link))));
                card.put("elements", elements);
                yield Map.of("msg_type", "interactive", "card", card);
            }
            case "slack" -> {
                List<Map<String, Object>> blocks = new ArrayList<>();
                blocks.add(Map.of("type", "section", "text",
                        Map.of("type", "mrkdwn", "text", "*" + summary + "*\n\n最近差评：\n" + comments)));
                blocks.add(Map.of("type", "actions", "elements", List.of(Map.of(
                        "type", "button", "text", Map.of("type", "plain_text", "content", "查看 Dashboard"),
                        "url", link))));
                yield Map.of("text", TITLE, "blocks", blocks);
            }
            case "dingtalk" -> Map.of(
                    "msgtype", "markdown",
                    "markdown", Map.of("title", TITLE,
                            "text", "**" + summary + "**\n\n最近差评：\n" + comments + "\n\n[查看 Dashboard](" + link + ")"));
            case "wecom" -> Map.of(
                    "msgtype", "markdown",
                    "markdown", Map.of("content", "**" + TITLE + "**\n\n" + summary + "\n\n最近差评：\n" + comments));
            default -> Map.of(
                    "title", TITLE, "summary", summary,
                    "comments", check.recentDownComments(),
                    "stats", check.stats(),
                    "dashboardUrl", link);
        };
    }
}
