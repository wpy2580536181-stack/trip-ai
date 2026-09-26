package com.trip.backend.web.handler;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.trip.backend.utils.AppException;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.sql.SQLException;
import java.util.HashMap;
import java.util.Map;

/**
 * 全局异常处理器（对应 Python exception_handlers.py）
 *
 * 异常映射规则：
 * - AppException → Format A/B（由 FormatResolver 判定）
 * - IntegrityError → 409 DUPLICATE_ENTRY / 400 FOREIGN_KEY_VIOLATION / 400 INTEGRITY_ERROR
 * - SQLException → 500（dev 泄漏 / prod 隐藏）
 * - JWT 失效 → 401（由 JwtAuthFilter 处理）
 * - auth/限流/守卫抛的 HTTPException → {"detail":...}（不经此 handler）
 * - 兜底 500
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    private final ObjectMapper objectMapper;
    private final boolean isProduction;

    public GlobalExceptionHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        // 从环境变量读取，默认为 production（隐藏错误详情）
        this.isProduction = !"development".equalsIgnoreCase(System.getenv("NODE_ENV"));
    }

    /**
     * 业务异常处理
     */
    @ExceptionHandler(AppException.class)
    public ResponseEntity<Map<String, Object>> handleAppException(AppException ex, HttpServletRequest request) {
        boolean formatA = FormatResolver.isFormatA(request);

        if (formatA) {
            // Format A: {success, data}
            Map<String, Object> body = new HashMap<>();
            body.put("success", false);
            body.put("data", null);
            return ResponseEntity.status(ex.getStatusCode())
                .body(body);
        } else {
            // Format B: {code, data, message, error}
            Map<String, Object> body = new HashMap<>();
            body.put("code", ex.getStatusCode());
            body.put("data", null);
            body.put("message", ex.getMessage());
            body.put("error", ex.getMessage());
            return ResponseEntity.status(ex.getStatusCode())
                .body(body);
        }
    }

    /**
     * 数据完整性异常（对应 Python IntegrityError）
     */
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<Map<String, Object>> handleDataIntegrityViolation(
            DataIntegrityViolationException ex, HttpServletRequest request) {
        boolean formatA = FormatResolver.isFormatA(request);
        String message;
        int statusCode;

        // 判断异常类型
        String rootMessage = ex.getRootCause() != null ? ex.getRootCause().getMessage() : ex.getMessage();
        if (rootMessage != null && rootMessage.contains("duplicate key")) {
            statusCode = 409;
            message = "DUPLICATE_ENTRY: " + extractDetail(rootMessage);
        } else if (rootMessage != null && (rootMessage.contains("foreign key") || rootMessage.contains("violates foreign key"))) {
            statusCode = 400;
            message = "FOREIGN_KEY_VIOLATION: " + extractDetail(rootMessage);
        } else {
            statusCode = 400;
            message = "INTEGRITY_ERROR: " + ex.getMessage();
        }

        if (formatA) {
            Map<String, Object> body = new HashMap<>();
            body.put("success", false);
            body.put("data", null);
            return ResponseEntity.status(statusCode)
                .body(body);
        } else {
            Map<String, Object> body = new HashMap<>();
            body.put("code", statusCode);
            body.put("data", null);
            body.put("message", message);
            body.put("error", message);
            return ResponseEntity.status(statusCode)
                .body(body);
        }
    }

    /**
     * SQL 异常（500）
     */
    @ExceptionHandler({BadSqlGrammarException.class, CannotGetJdbcConnectionException.class, SQLException.class})
    public ResponseEntity<Map<String, Object>> handleSqlException(Exception ex, HttpServletRequest request) {
        boolean formatA = FormatResolver.isFormatA(request);

        if (isProduction) {
            // production: 隐藏错误详情
            if (formatA) {
                Map<String, Object> body = new HashMap<>();
                body.put("success", false);
                body.put("data", null);
                return ResponseEntity.status(500).body(body);
            } else {
                Map<String, Object> body = new HashMap<>();
                body.put("code", 500);
                body.put("data", null);
                body.put("message", "Internal Server Error");
                body.put("error", "Internal Server Error");
                return ResponseEntity.status(500)
                    .body(body);
            }
        } else {
            // development: 泄漏错误详情
            if (formatA) {
                Map<String, Object> body = new HashMap<>();
                body.put("success", false);
                body.put("data", null);
                return ResponseEntity.status(500).body(body);
            } else {
                Map<String, Object> body = new HashMap<>();
                body.put("code", 500);
                body.put("data", null);
                body.put("message", ex.getMessage());
                body.put("error", ex.getMessage());
                return ResponseEntity.status(500)
                    .body(body);
            }
        }
    }

    /**
     * 兜底 500
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleException(Exception ex, HttpServletRequest request) {
        System.err.println("[UNHANDLED-500] " + request.getRequestURI());
        ex.printStackTrace(System.err);
        boolean formatA = FormatResolver.isFormatA(request);

        if (isProduction) {
            if (formatA) {
                Map<String, Object> body = new HashMap<>();
                body.put("success", false);
                body.put("data", null);
                return ResponseEntity.status(500).body(body);
            } else {
                Map<String, Object> body = new HashMap<>();
                body.put("code", 500);
                body.put("data", null);
                body.put("message", "Internal Server Error");
                body.put("error", "Internal Server Error");
                return ResponseEntity.status(500)
                    .body(body);
            }
        } else {
            if (formatA) {
                Map<String, Object> body = new HashMap<>();
                body.put("success", false);
                body.put("data", null);
                return ResponseEntity.status(500).body(body);
            } else {
                Map<String, Object> body = new HashMap<>();
                body.put("code", 500);
                body.put("data", null);
                body.put("message", ex.getMessage());
                body.put("error", ex.getMessage());
                return ResponseEntity.status(500)
                    .body(body);
            }
        }
    }

    private String extractDetail(String message) {
        // 提取 PostgreSQL 错误详情
        if (message == null) return "";
        int idx = message.indexOf("\n");
        return idx > 0 ? message.substring(0, idx) : message;
    }
}
