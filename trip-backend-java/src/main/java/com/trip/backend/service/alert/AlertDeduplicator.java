package com.trip.backend.service.alert;

import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 告警去重器（对应 Python alert_deduplicator.py）。
 *
 * <p>基于 md5(alertType:keyInfo) 指纹，冷却期内相同告警不重复发送。
 * 默认冷却 3600s；可注入自定义时钟便于测试。
 */
@Component
public class AlertDeduplicator {

    public static final long DEFAULT_COOLDOWN_SECONDS = 3600;

    private final long cooldownSeconds;
    private final Map<String, Long> store = new ConcurrentHashMap<>();

    public AlertDeduplicator() {
        this(DEFAULT_COOLDOWN_SECONDS);
    }

    public AlertDeduplicator(long cooldownSeconds) {
        this.cooldownSeconds = cooldownSeconds;
    }

    public String fingerprint(String alertType, String keyInfo) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] raw = (alertType + ":" + (keyInfo == null ? "" : keyInfo)).getBytes(StandardCharsets.UTF_8);
            return HexFormat.of().formatHex(md.digest(raw));
        } catch (Exception e) {
            throw new IllegalStateException("md5 unavailable", e);
        }
    }

    /** 原子判断：若不在冷却期则记录并返回 true（应发送），否则返回 false。 */
    public boolean shouldSend(String alertType, String keyInfo) {
        return shouldSend(alertType, keyInfo, System.currentTimeMillis() / 1000);
    }

    public synchronized boolean shouldSend(String alertType, String keyInfo, long nowEpochSec) {
        String fp = fingerprint(alertType, keyInfo);
        Long expiresAt = store.get(fp);
        if (expiresAt != null && expiresAt > nowEpochSec) {
            return false; // 冷却中
        }
        store.put(fp, nowEpochSec + cooldownSeconds);
        return true;
    }
}
