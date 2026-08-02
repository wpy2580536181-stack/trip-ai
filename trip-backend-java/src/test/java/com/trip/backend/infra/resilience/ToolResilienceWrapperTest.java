package com.trip.backend.infra.resilience;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * ToolResilienceWrapper 测试
 */
class ToolResilienceWrapperTest {

    @Test
    void testExecuteSuccess() throws Exception {
        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(5_000)
            .retries(0)
            .fallback("fallback")
            .build();

        String result = wrapper.execute(() -> "success");

        assertThat(result).isEqualTo("success");
    }

    @Test
    void testExecuteTimeout() throws Exception {
        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(1_000)
            .retries(0)
            .fallback("fallback")
            .build();

        String result = wrapper.execute(() -> {
            Thread.sleep(2_000); // 超时
            return "should not reach here";
        });

        assertThat(result).isEqualTo("fallback");
    }

    @Test
    void testExecuteFailure() throws Exception {
        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(5_000)
            .retries(0)
            .fallback("fallback")
            .build();

        String result = wrapper.execute(() -> {
            throw new RuntimeException("test error");
        });

        assertThat(result).isEqualTo("fallback");
    }

    @Test
    void testExecuteWithRetry() throws Exception {
        // 模拟前两次失败，第三次成功
        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(5_000)
            .retries(2)
            .fallback("fallback")
            .build();

        // TODO: 需要使用 mock 才能精确控制重试次数
    }

    @Test
    void testExecuteWithCircuitBreakerOpen() {
        CircuitBreaker breaker = new CircuitBreaker("test_cb", 2, 60_000);

        ToolResilienceWrapper wrapper = ToolResilienceWrapper.builder()
            .timeout(5_000)
            .retries(0)
            .fallback("fallback")
            .circuitBreaker(breaker)
            .build();

        // 触发熔断
        breaker.recordFailure();
        breaker.recordFailure();

        String result = wrapper.execute(() -> {
            throw new RuntimeException("should not be called");
        });

        assertThat(result).isEqualTo("fallback");
    }
}
