package com.trip.backend.infra.cache;

import org.springframework.stereotype.Component;

import java.security.MessageDigest;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

/**
 * LLM 缓存（对应 Python llm_cache.py）
 * - key: llm_cache:{sha256(prompt)[:32]}
 * - TTL: 600s
 */
@Component
public class LlmCache {

    private final DualBackendCache cache;

    public LlmCache(DualBackendCache cache) {
        this.cache = cache;
    }

    public void put(String prompt, String response) {
        String key = "llm_cache:" + sha256(prompt).substring(0, 32);
        cache.put(key, response, 600, TimeUnit.SECONDS);
    }

    public Optional<String> get(String prompt) {
        String key = "llm_cache:" + sha256(prompt).substring(0, 32);
        return cache.get(key);
    }

    private String sha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(input.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder hexString = new StringBuilder();
            for (byte b : hash) {
                String hex = Integer.toHexString(0xff & b);
                if (hex.length() == 1) hexString.append('0');
                hexString.append(hex);
            }
            return hexString.toString();
        } catch (Exception e) {
            throw new RuntimeException("SHA-256 计算失败", e);
        }
    }
}
