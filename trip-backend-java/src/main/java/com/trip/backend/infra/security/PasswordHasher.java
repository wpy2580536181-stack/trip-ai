package com.trip.backend.infra.security;

import org.mindrot.jbcrypt.BCrypt;
import org.springframework.stereotype.Component;

/**
 * 密码哈希工具（对应 Python utils/security.py）
 * - bcrypt rounds=12
 */
@Component
public class PasswordHasher {

    private static final int ROUNDS = 12;

    /**
     * 哈希密码
     */
    public String hash(char[] password) {
        return BCrypt.hashpw(new String(password), BCrypt.gensalt(ROUNDS));
    }

    /**
     * 哈希密码（String 版本）
     */
    public String hash(String password) {
        return BCrypt.hashpw(password, BCrypt.gensalt(ROUNDS));
    }

    /**
     * 验证密码
     */
    public boolean verify(char[] password, String hashed) {
        return BCrypt.checkpw(new String(password), hashed);
    }

    /**
     * 验证密码（String 版本）
     */
    public boolean verify(String password, String hashed) {
        return BCrypt.checkpw(password, hashed);
    }
}
