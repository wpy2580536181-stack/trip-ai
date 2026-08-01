package com.trip.backend.utils;

/**
 * 业务异常基类（对应 Python 的 AppException）
 * Format A: {success, data}（仅 /api/trip/recommend 路径）
 * Format B: {code, data, message, error}（通用路径）
 */
public class AppException extends RuntimeException {

    private final int statusCode;

    public AppException(String message) {
        super(message);
        this.statusCode = 400;
    }

    public AppException(String message, int statusCode) {
        super(message);
        this.statusCode = statusCode;
    }

    public int getStatusCode() {
        return statusCode;
    }

    // 快捷工厂方法
    public static AppException notFound(String message) {
        return new AppException(message, 404);
    }

    public static AppException unauthorized(String message) {
        return new AppException(message, 401);
    }

    public static AppException forbidden(String message) {
        return new AppException(message, 403);
    }

    public static AppException badRequest(String message) {
        return new AppException(message, 400);
    }

    public static AppException conflict(String message) {
        return new AppException(message, 409);
    }

    public static AppException duplicateEntry(String message) {
        return new AppException(message, 409);
    }

    public static AppException foreignKeyViolation(String message) {
        return new AppException(message, 400);
    }
}
