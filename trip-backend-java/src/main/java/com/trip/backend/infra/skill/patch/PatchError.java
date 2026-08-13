package com.trip.backend.infra.skill.patch;

/**
 * Patch 应用失败异常，应降级为 modify
 *
 * 对应 Python: class PatchError(Exception)
 */
public class PatchError extends RuntimeException {
    public PatchError(String message) {
        super(message);
    }

    public PatchError(String message, Throwable cause) {
        super(message, cause);
    }
}
