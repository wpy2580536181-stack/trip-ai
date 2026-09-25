package com.trip.backend.service.alert;

import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * J-E1 告警系统判定：
 * 1) 5 种 webhook payload 结构正确；
 * 2) rate=up/(up+down)，total>=5 且 rate<0.5 触发；
 * 3) md5 指纹冷却 3600s 内不重复发送。
 */
class AlertSystemTest {

    private final AlertDetector detector = new AlertDetector();
    private final AlertWebhook webhook = new AlertWebhook();

    private AlertCheckResult check(int up, int down) {
        return detector.check(up, down, List.of());
    }

    @Test
    void triggersWhenTotalEnoughAndRateBelowThreshold() {
        // total=6, up=2/down=4 -> rate=0.33 < 0.5 -> 触发
        AlertCheckResult r = check(2, 4);
        assertTrue(r.shouldAlert(), "total>=5 且 rate<0.5 应触发");
        assertEquals(0.333333, (double) r.stats().get("satisfactionRate"), 1e-4);
    }

    @Test
    void noTriggerWhenSampleTooSmall() {
        // total=4 < 5 -> 即使 rate=0 也不触发
        assertFalse(check(0, 4).shouldAlert(), "样本不足应不触发");
    }

    @Test
    void noTriggerWhenRateHealthy() {
        // up=5/down=1 -> rate=0.83 >= 0.5 -> 不触发
        assertFalse(check(5, 1).shouldAlert());
    }

    @Test
    void rateIsUpOverTotal() {
        AlertCheckResult r = check(3, 7);
        assertEquals(10, r.stats().get("feedbackCount"));
        assertEquals(0.3, (double) r.stats().get("satisfactionRate"), 1e-9);
    }

    @Test
    void fiveWebhookPayloadsStructured() {
        AlertCheckResult r = detector.check(1, 5,
                List.of(Map.of("comment", "太慢了", "tags", List.of("speed"))));
        String dash = "http://localhost:8080";

        Map<String, Object> feishu = webhook.formatPayload("feishu", r, dash);
        assertEquals("interactive", feishu.get("msg_type"));
        assertTrue(((Map<?, ?>) feishu.get("card")).containsKey("elements"));

        Map<String, Object> slack = webhook.formatPayload("slack", r, dash);
        assertEquals("⚠️ Feedback 满意率告警", slack.get("text"));
        assertTrue(((List<?>) slack.get("blocks")).size() >= 2);

        Map<String, Object> dingtalk = webhook.formatPayload("dingtalk", r, dash);
        assertEquals("markdown", dingtalk.get("msgtype"));
        assertTrue(((Map<?, ?>) dingtalk.get("markdown")).get("text").toString().contains("admin/feedback"));

        Map<String, Object> wecom = webhook.formatPayload("wecom", r, dash);
        assertEquals("markdown", wecom.get("msgtype"));

        Map<String, Object> custom = webhook.formatPayload("custom", r, dash);
        assertEquals("http://localhost:8080/admin/feedback", custom.get("dashboardUrl"));
        assertTrue(custom.containsKey("stats"));
    }

    @Test
    void dedupCooldownBlocksRepeatWithin3600s() {
        AlertDeduplicator dedup = new AlertDeduplicator(3600);
        long t0 = 1_000_000;
        assertTrue(dedup.shouldSend("feedback_low", "city=cd", t0));
        assertFalse(dedup.shouldSend("feedback_low", "city=cd", t0 + 1800), "1800s 内应冷却");
        assertTrue(dedup.shouldSend("feedback_low", "city=cd", t0 + 3601), "3601s 后应放行");
        // 不同 keyInfo 不受影响
        assertTrue(dedup.shouldSend("feedback_low", "city=sh", t0));
    }
}
