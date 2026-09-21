package com.trip.backend.service.llm;

/**
 * LLM 调用超时异常（对应 Python asyncio.wait_for TimeoutError）。
 */
public class LlmTimeoutException extends RuntimeException {

    public LlmTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
