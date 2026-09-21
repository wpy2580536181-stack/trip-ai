package com.trip.backend.service.agent.tools;

/**
 * 上游 429 限流异常（对应 Python httpx.HTTPStatusError status=429）。
 * 携带 Retry-After 秒数，供 ResilienceWrapper 计算退避。
 */
public class RateLimitException extends RuntimeException {

    private final long retryAfterSec;

    public RateLimitException(long retryAfterSec) {
        super("rate limited (429), retry-after=" + retryAfterSec + "s");
        this.retryAfterSec = Math.max(0, retryAfterSec);
    }

    public long retryAfterSec() {
        return retryAfterSec;
    }
}
