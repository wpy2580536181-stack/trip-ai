package com.trip.backend.infra.task;

import org.springframework.beans.factory.annotation.Autowired;

import java.time.Duration;
import java.util.List;

/**
 * 任务重试策略（对齐 Python arq worker 配置）。
 *
 * - max_tries = 3：最多尝试 3 次
 * - 退避 1s → 2s → 4s（指数退避）
 * - job_timeout = 300s：单次执行超时视为失败
 */
import org.springframework.stereotype.Component;

@Component
public class RetryPolicy {

    public static final int DEFAULT_MAX_TRIES = 3;
    public static final Duration DEFAULT_JOB_TIMEOUT = Duration.ofSeconds(300);
    public static final List<Duration> DEFAULT_BACKOFF = List.of(
        Duration.ofSeconds(1),
        Duration.ofSeconds(2),
        Duration.ofSeconds(4)
    );

    private final int maxTries;
    private final List<Duration> backoffDelays;
    private final Duration jobTimeout;

    public RetryPolicy() {
        this(DEFAULT_MAX_TRIES, DEFAULT_BACKOFF, DEFAULT_JOB_TIMEOUT);
    }

    public RetryPolicy(int maxTries, List<Duration> backoffDelays, Duration jobTimeout) {
        this.maxTries = maxTries;
        this.backoffDelays = List.copyOf(backoffDelays);
        this.jobTimeout = jobTimeout;
    }

    /** 第 {@code attempt} 次失败后的退避时长（attempt 从 1 开始，超界时取最后一个）。 */
    public Duration delayForTry(int attempt) {
        if (attempt <= 0) {
            return backoffDelays.get(0);
        }
        int index = Math.min(attempt, backoffDelays.size()) - 1;
        return backoffDelays.get(index);
    }

    public int getMaxTries() {
        return maxTries;
    }

    public List<Duration> getBackoffDelays() {
        return backoffDelays;
    }

    public Duration getJobTimeout() {
        return jobTimeout;
    }
}
