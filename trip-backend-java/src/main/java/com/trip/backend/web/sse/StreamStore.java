package com.trip.backend.web.sse;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Stream 存储（对应 Python stream_store.py）
 * - Redis 优先（TTL 600s）
 * - 内存降级
 * - 断点续传支持
 */
@Component
public class StreamStore {

    private final StringRedisTemplate redisTemplate;
    private final boolean redisAvailable;

    // Redis key 前缀
    private static final String STREAM_PREFIX = "stream:";
    private static final String EVENTS_PREFIX = ":events";
    private static final String SEQ_PREFIX = ":seq";
    private static final long TTL_SECONDS = 600;

    // 内存降级存储
    private final ConcurrentHashMap<String, StreamEntry> memoryStore = new ConcurrentHashMap<>();

    public StreamStore(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
        this.redisAvailable = checkRedisAvailable();
    }

    private boolean checkRedisAvailable() {
        try {
            redisTemplate.opsForValue().get("health-check");
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 创建新 Stream
     */
    public StreamState createStream(String userId, String conversationId) {
        String streamId = java.util.UUID.randomUUID().toString();

        if (redisAvailable) {
            createStreamRedis(streamId, userId, conversationId);
        } else {
            createStreamMemory(streamId, userId, conversationId);
        }

        return new StreamState(streamId, 0);
    }

    private void createStreamRedis(String streamId, String userId, String conversationId) {
        String hashKey = STREAM_PREFIX + streamId;
        redisTemplate.opsForHash().putAll(hashKey, java.util.Map.of(
            "userId", userId,
            "conversationId", conversationId,
            "status", "active",
            "createdAt", Instant.now().toString(),
            "lastEventAt", Instant.now().toString()
        ));
        redisTemplate.expire(hashKey, TTL_SECONDS, java.util.concurrent.TimeUnit.SECONDS);
        redisTemplate.opsForValue().set(SEQ_PREFIX + streamId, "0");
        redisTemplate.expire(SEQ_PREFIX + streamId, TTL_SECONDS, java.util.concurrent.TimeUnit.SECONDS);
    }

    private void createStreamMemory(String streamId, String userId, String conversationId) {
        memoryStore.put(streamId, new StreamEntry(userId, conversationId, new ArrayList<>(), 0));
    }

    /**
     * 追加事件
     */
    public long appendEvent(String streamId, String eventType, String eventData) {
        if (redisAvailable) {
            return appendEventRedis(streamId, eventType, eventData);
        } else {
            return appendEventMemory(streamId, eventType, eventData);
        }
    }

    private long appendEventRedis(String streamId, String eventType, String eventData) {
        try {
            // 自增序列号
            Long seq = redisTemplate.opsForValue().increment(SEQ_PREFIX + streamId);
            if (seq == null) {
                throw new IllegalStateException("Stream not found: " + streamId);
            }

            // 追加事件
            String eventJson = String.format("{\"seq\":%d,\"type\":\"%s\",\"data\":%s}", seq, eventType, eventData);
            redisTemplate.opsForList().rightPush(EVENTS_PREFIX + streamId, eventJson);

            // 续期 TTL
            redisTemplate.expire(SEQ_PREFIX + streamId, TTL_SECONDS, java.util.concurrent.TimeUnit.SECONDS);
            redisTemplate.expire(EVENTS_PREFIX + streamId, TTL_SECONDS, java.util.concurrent.TimeUnit.SECONDS);
            redisTemplate.expire(STREAM_PREFIX + streamId, TTL_SECONDS, java.util.concurrent.TimeUnit.SECONDS);

            return seq;
        } catch (Exception e) {
            // Redis 异常，降级内存
            return appendEventMemory(streamId, eventType, eventData);
        }
    }

    private long appendEventMemory(String streamId, String eventType, String eventData) {
        StreamEntry entry = memoryStore.get(streamId);
        if (entry == null) {
            throw new IllegalStateException("Stream not found: " + streamId);
        }

        long seq = entry.nextSeq++;
        entry.events.add(new StreamEvent(seq, eventType, eventData));
        return seq;
    }

    /**
     * 获取指定序列号之后的事件（断点续传）
     */
    public List<StreamEvent> getEventsSince(String streamId, long lastSeq) {
        if (redisAvailable) {
            return getEventsSinceRedis(streamId, lastSeq);
        } else {
            return getEventsSinceMemory(streamId, lastSeq);
        }
    }

    private List<StreamEvent> getEventsSinceRedis(String streamId, long lastSeq) {
        List<StreamEvent> events = new ArrayList<>();
        try {
            Long totalSeq = getTotalSeqRedis(streamId);
            if (totalSeq == null) {
                throw new StreamNotFoundException(streamId);
            }

            if (lastSeq > totalSeq) {
                throw new IllegalArgumentException("lastSeq > totalSeq");
            }

            if (lastSeq >= totalSeq) {
                return events; // 空列表
            }

            // LRANGE lastSeq -1（从 0 开始索引）
            List<String> eventJsons = redisTemplate.opsForList().range(EVENTS_PREFIX + streamId, lastSeq, -1);
            if (eventJsons != null) {
                for (String json : eventJsons) {
                    try {
                        com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
                        var node = mapper.readTree(json);
                        long seq = node.get("seq").asLong();
                        String type = node.get("type").asText();
                        String data = node.get("data").toString();
                        events.add(new StreamEvent(seq, type, data));
                    } catch (Exception e) {
                        // 解析失败，跳过
                    }
                }
            }

            return events;
        } catch (Exception e) {
            throw new RuntimeException("Failed to get events from Redis", e);
        }
    }

    private List<StreamEvent> getEventsSinceMemory(String streamId, long lastSeq) {
        StreamEntry entry = memoryStore.get(streamId);
        if (entry == null) {
            throw new StreamNotFoundException(streamId);
        }

        List<StreamEvent> events = new ArrayList<>();
        for (StreamEvent event : entry.events) {
            if (event.seq() > lastSeq) {
                events.add(event);
            }
        }
        return events;
    }

    /**
     * 获取 Stream 状态（IDOR 校验用）
     */
    public StreamState getStreamState(String streamId) throws StreamNotFoundException {
        if (redisAvailable) {
            return getStreamStateRedis(streamId);
        } else {
            return getStreamStateMemory(streamId);
        }
    }

    private StreamState getStreamStateRedis(String streamId) throws StreamNotFoundException {
        var hash = redisTemplate.opsForHash().entries(STREAM_PREFIX + streamId);
        if (hash.isEmpty()) {
            throw new StreamNotFoundException(streamId);
        }

        String userId = (String) hash.get("userId");
        Long totalSeq = getTotalSeqRedis(streamId);
        return new StreamState(streamId, totalSeq != null ? totalSeq : 0);
    }

    private StreamState getStreamStateMemory(String streamId) throws StreamNotFoundException {
        StreamEntry entry = memoryStore.get(streamId);
        if (entry == null) {
            throw new StreamNotFoundException(streamId);
        }
        return new StreamState(streamId, entry.nextSeq - 1);
    }

    /**
     * 标记完成
     */
    public void markComplete(String streamId) {
        if (redisAvailable) {
            redisTemplate.opsForHash().put(STREAM_PREFIX + streamId, "status", "completed");
        } else {
            StreamEntry entry = memoryStore.get(streamId);
            if (entry != null) {
                entry.status = "completed";
            }
        }
    }

    /**
     * 删除 Stream
     */
    public void deleteStream(String streamId) {
        if (redisAvailable) {
            redisTemplate.delete(STREAM_PREFIX + streamId);
            redisTemplate.delete(EVENTS_PREFIX + streamId);
            redisTemplate.delete(SEQ_PREFIX + streamId);
        } else {
            memoryStore.remove(streamId);
        }
    }

    private Long getTotalSeqRedis(String streamId) {
        String seqStr = redisTemplate.opsForValue().get(SEQ_PREFIX + streamId);
        return seqStr != null ? Long.parseLong(seqStr) : 0;
    }

    // 内部类

    private static class StreamEntry {
        String userId;
        String conversationId;
        String status;
        List<StreamEvent> events;
        long nextSeq;

        StreamEntry(String userId, String conversationId, List<StreamEvent> events, long nextSeq) {
            this.userId = userId;
            this.conversationId = conversationId;
            this.events = events;
            this.nextSeq = nextSeq;
            this.status = "active";
        }
    }

    public record StreamEvent(long seq, String type, String data) {}
    public record StreamState(String streamId, long totalSeq) {}

    public static class StreamNotFoundException extends RuntimeException {
        public StreamNotFoundException(String streamId) {
            super("Stream not found: " + streamId);
        }
    }
}
