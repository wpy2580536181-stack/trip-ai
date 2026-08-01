package com.trip.backend.web.controller;

import com.trip.backend.domain.entity.User;
import com.trip.backend.service.UserService;
import com.trip.backend.utils.AppException;
import com.trip.backend.web.handler.FormatResolver;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

import java.util.Map;

/**
 * 用户认证控制器（对应 Python routers/user.py）
 * 7 个端点：
 * - POST /api/user/register（公开）
 * - POST /api/user/login（公开）
 * - GET /api/user/info（JWT）
 * - PUT /api/user/info（JWT）
 * - PUT /api/user/password（JWT）
 * - POST /api/user/forgot-password（公开）
 * - POST /api/user/reset-password（公开）
 */
@RestController
@RequestMapping("/api/user")
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    /**
     * POST /api/user/register
     */
    @PostMapping("/register")
    public ResponseEntity<Map<String, Object>> register(
            @Valid @RequestBody RegisterRequest request,
            HttpServletRequest httpRequest) {
        User user = userService.register(request.username, request.email, request.password);

        Map<String, Object> data = Map.of(
            "id", user.getId(),
            "username", user.getUsername(),
            "email", user.getEmail()
        );

        if (FormatResolver.isFormatA(httpRequest)) {
            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.status(HttpStatus.CREATED).body(Map.of(
                "code", 201, "data", data, "message", "注册成功", "error", null
            ));
        }
    }

    /**
     * POST /api/user/login
     */
    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(
            @Valid @RequestBody LoginRequest request,
            HttpServletRequest httpRequest) {
        User user = userService.login(request.identifier, request.password);

        // 生成 JWT（简化版，实际应调用 JwtService）
        // TODO: 注入 JwtUtil 生成 token
        String token = "mock-jwt-token-" + user.getId(); // 临时占位

        Map<String, Object> data = Map.of(
            "token", token,
            "user", Map.of(
                "id", user.getId(),
                "username", user.getUsername(),
                "email", user.getEmail(),
                "nickname", user.getNickname(),
                "avatar", user.getAvatar()
            )
        );

        if (FormatResolver.isFormatA(httpRequest)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200, "data", data, "message", "登录成功", "error", null
            ));
        }
    }

    /**
     * GET /api/user/info
     */
    @GetMapping("/info")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> getInfo(
            @RequestAttribute("userId") Long userId,
            HttpServletRequest httpRequest) {
        User user = userService.getUserInfo(userId);

        Map<String, Object> data = Map.of(
            "id", user.getId(),
            "username", user.getUsername(),
            "email", user.getEmail(),
            "nickname", user.getNickname(),
            "avatar", user.getAvatar(),
            "bio", user.getBio()
        );

        if (FormatResolver.isFormatA(httpRequest)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200, "data", data, "message", null, "error", null
            ));
        }
    }

    /**
     * PUT /api/user/info
     */
    @PutMapping("/info")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> updateInfo(
            @RequestAttribute("userId") Long userId,
            @Valid @RequestBody UpdateInfoRequest request,
            HttpServletRequest httpRequest) {
        User user = userService.updateUserInfo(userId, request.nickname, request.avatar, request.bio);

        Map<String, Object> data = Map.of(
            "id", user.getId(),
            "username", user.getUsername(),
            "email", user.getEmail(),
            "nickname", user.getNickname(),
            "avatar", user.getAvatar(),
            "bio", user.getBio()
        );

        if (FormatResolver.isFormatA(httpRequest)) {
            return ResponseEntity.ok(Map.of("success", true, "data", data));
        } else {
            return ResponseEntity.ok(Map.of(
                "code", 200, "data", data, "message", null, "error", null
            ));
        }
    }

    /**
     * PUT /api/user/password
     */
    @PutMapping("/password")
    @PreAuthorize("isAuthenticated()")
    public ResponseEntity<Map<String, Object>> changePassword(
            @RequestAttribute("userId") Long userId,
            @Valid @RequestBody ChangePasswordRequest request) {
        userService.changePassword(userId, request.oldPassword, request.newPassword);
        return ResponseEntity.ok(Map.of("success", true, "data", null));
    }

    /**
     * POST /api/user/forgot-password（恒返回成功，防枚举）
     */
    @PostMapping("/forgot-password")
    public ResponseEntity<Map<String, Object>> forgotPassword(
            @Valid @RequestBody ForgotPasswordRequest request) {
        userService.forgotPassword(request.email);
        return ResponseEntity.ok(Map.of("success", true, "data", null));
    }

    /**
     * POST /api/user/reset-password
     */
    @PostMapping("/reset-password")
    public ResponseEntity<Map<String, Object>> resetPassword(
            @Valid @RequestBody ResetPasswordRequest request) {
        userService.resetPassword(request.token, request.newPassword);
        return ResponseEntity.ok(Map.of("success", true, "data", null));
    }

    // ========== DTOs ==========

    public record RegisterRequest(
        @NotBlank @Size(min = 3, max = 50) String username,
        @NotBlank @Email String email,
        @NotBlank @Size(min = 6) String password
    ) {}

    public record LoginRequest(
        @NotBlank String identifier,
        @NotBlank String password
    ) {}

    public record UpdateInfoRequest(
        @Size(max = 50) String nickname,
        String avatar,
        @Size(max = 255) String bio
    ) {}

    public record ChangePasswordRequest(
        @NotBlank String oldPassword,
        @NotBlank @Size(min = 6) String newPassword
    ) {}

    public record ForgotPasswordRequest(
        @NotBlank @Email String email
    ) {}

    public record ResetPasswordRequest(
        @NotBlank String token,
        @NotBlank @Size(min = 6) String newPassword
    ) {}
}
