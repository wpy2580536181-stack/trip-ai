package com.trip.backend.service;

import com.trip.backend.domain.entity.PasswordReset;
import com.trip.backend.domain.entity.Role;
import com.trip.backend.domain.entity.User;
import com.trip.backend.domain.repository.PasswordResetRepository;
import com.trip.backend.domain.repository.RoleRepository;
import com.trip.backend.domain.repository.UserRepository;
import com.trip.backend.infra.security.PasswordHasher;
import com.trip.backend.utils.AppException;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.Optional;
import java.util.UUID;

/**
 * 用户服务（对应 Python services/user_service.py）
 */
@Service
public class UserService {

    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final PasswordResetRepository passwordResetRepository;
    private final PasswordHasher passwordHasher;

    public UserService(UserRepository userRepository,
                      RoleRepository roleRepository,
                      PasswordResetRepository passwordResetRepository,
                      PasswordHasher passwordHasher) {
        this.userRepository = userRepository;
        this.roleRepository = roleRepository;
        this.passwordResetRepository = passwordResetRepository;
        this.passwordHasher = passwordHasher;
    }

    /**
     * 注册
     */
    public User register(String username, String email, String password) {
        // 查重
        if (userRepository.existsByUsername(username)) {
            throw AppException.badRequest("用户名已存在");
        }
        if (userRepository.existsByEmail(email)) {
            throw AppException.badRequest("邮箱已被注册");
        }

        // 创建用户
        User user = new User();
        user.setUsername(username);
        user.setEmail(email);
        user.setPassword(passwordHasher.hash(password));

        // 默认角色（USER）
        Role userRole = roleRepository.findByName("USER")
            .orElseThrow(() -> AppException.internalServerError("默认角色不存在"));
        user.setRoleId(userRole.getId());

        return userRepository.save(user);
    }

    /**
     * 登录（支持用户名或邮箱）
     */
    public User login(String identifier, String password) {
        Optional<User> userOpt = userRepository.findByUsername(identifier);
        if (userOpt.isEmpty()) {
            userOpt = userRepository.findByEmail(identifier);
        }
        if (userOpt.isEmpty()) {
            throw AppException.unauthorized("用户名或邮箱不存在");
        }

        User user = userOpt.get();
        if (!passwordHasher.verify(password, user.getPassword())) {
            throw AppException.unauthorized("密码错误");
        }

        if (user.getStatus() == 0) {
            throw AppException.forbidden("账户已禁用");
        }

        return user;
    }

    /**
     * 修改密码
     */
    public void changePassword(Long userId, String oldPassword, String newPassword) {
        User user = userRepository.findById(userId)
            .orElseThrow(() -> AppException.notFound("用户不存在"));

        if (!passwordHasher.verify(oldPassword, user.getPassword())) {
            throw AppException.badRequest("旧密码错误");
        }

        user.setPassword(passwordHasher.hash(newPassword));
        userRepository.save(user);
    }

    /**
     * 忘记密码（恒返回成功，防枚举）
     */
    public void forgotPassword(String email) {
        // 检查用户是否存在
        Optional<User> userOpt = userRepository.findByEmail(email);
        if (userOpt.isPresent()) {
            // 生成重置令牌（仅日志，不发邮件）
            String token = UUID.randomUUID().toString();
            OffsetDateTime expiresAt = OffsetDateTime.now().plusMinutes(30);

            PasswordReset reset = new PasswordReset(email, token, expiresAt);
            passwordResetRepository.save(reset);

            // TODO: 实际发送邮件（当前仅日志）
            System.out.println("[ forgot_password ] token=" + token + " email=" + email);
        }

        // 恒返回成功（防枚举）
    }

    /**
     * 重置密码
     */
    public void resetPassword(String token, String newPassword) {
        PasswordReset reset = passwordResetRepository.findByToken(token)
            .orElseThrow(() -> AppException.badRequest("重置令牌无效"));

        if (!reset.isValid()) {
            throw AppException.badRequest("重置令牌已过期或已使用");
        }

        // 更新用户密码
        User user = userRepository.findByEmail(reset.getEmail())
            .orElseThrow(() -> AppException.badRequest("用户不存在"));

        user.setPassword(passwordHasher.hash(newPassword));
        userRepository.save(user);

        // 标记令牌已使用
        reset.setUsed(true);
        passwordResetRepository.save(reset);
    }

    /**
     * 获取用户信息
     */
    public User getUserInfo(Long userId) {
        return userRepository.findById(userId)
            .orElseThrow(() -> AppException.notFound("用户不存在"));
    }

    /**
     * 更新用户信息
     */
    public User updateUserInfo(Long userId, String nickname, String avatar, String bio) {
        User user = userRepository.findById(userId)
            .orElseThrow(() -> AppException.notFound("用户不存在"));

        if (nickname != null) user.setNickname(nickname);
        if (avatar != null) user.setAvatar(avatar);
        if (bio != null) user.setBio(bio);

        return userRepository.save(user);
    }
}
