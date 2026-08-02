package com.trip.backend.infra.resilience;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * CircuitBreaker 测试
 */
class CircuitBreakerTest {

    private CircuitBreaker breaker;

    @BeforeEach
    void setUp() {
        breaker = new CircuitBreaker("test", 5, 30_000);
    }

    @Test
    void testClosedState() {
        // CLOSED 状态允许请求
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        assertThat(breaker.allowRequest()).isTrue();
    }

    @Test
    void testClosedToOpen() {
        // 连续失败 5 次 → OPEN
        for (int i = 0; i < 5; i++) {
            breaker.recordFailure();
        }

        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(breaker.getFailureCount()).isEqualTo(5);
        assertThat(breaker.allowRequest()).isFalse();
    }

    @Test
    void testOpenToHalfOpen() {
        breaker.recordFailure();
        breaker.recordFailure();
        breaker.recordFailure();
        breaker.recordFailure();
        breaker.recordFailure();
        breaker.recordFailure();

        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // 手动快速进入 HALF_OPEN
        breaker = new CircuitBreaker("test2", 2, 0); // 0ms 超时立即 HALF_OPEN
        breaker.recordFailure();
        breaker.recordFailure();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // 允许请求通过（HALF_OPEN）
        assertThat(breaker.allowRequest()).isTrue();
    }

    @Test
    void testHalfOpenToClosed() {
        CircuitBreaker breaker = new CircuitBreaker("test3", 2, 0);

        // 触发熔断
        breaker.recordFailure();
        breaker.recordFailure();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        // 进入 HALF_OPEN
        assertThat(breaker.allowRequest()).isTrue();

        // 记录成功 → CLOSED
        breaker.recordSuccess();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        assertThat(breaker.getFailureCount()).isEqualTo(0);
    }

    @Test
    void testGetOrCreate() {
        CircuitBreaker b1 = CircuitBreaker.getOrCreate("test", 5, 30_000);
        CircuitBreaker b2 = CircuitBreaker.getOrCreate("test", 5, 30_000);

        assertThat(b1).isSameAs(b2);
    }

    @Test
    void testRecordSuccessInClosed() {
        breaker.recordSuccess();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        assertThat(breaker.getFailureCount()).isEqualTo(0);
    }
}
