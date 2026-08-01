package com.trip.backend.web.handler;

import jakarta.servlet.http.HttpServletRequest;

/**
 * 响应格式解析器
 * Format A: {success, data}（仅 /api/trip/recommend 路径）
 * Format B: {code, data, message, error}（通用路径）
 */
public class FormatResolver {

    private static final String RECOMMEND_PATH_PREFIX = "/api/trip/recommend";

    /**
     * 判断是否使用 Format A
     * @param request HTTP 请求
     * @return true 表示使用 Format A，false 表示使用 Format B
     */
    public static boolean isFormatA(HttpServletRequest request) {
        String path = request.getRequestURI();
        // recommend-stream 因前缀 startswith 亦命中
        return path != null && path.startsWith(RECOMMEND_PATH_PREFIX);
    }

    /**
     * 判断是否使用 Format A（兼容 String 路径）
     */
    public static boolean isFormatA(String requestURI) {
        return requestURI != null && requestURI.startsWith(RECOMMEND_PATH_PREFIX);
    }
}
