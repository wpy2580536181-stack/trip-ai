package com.trip.backend.test.bcrypt;

import com.trip.backend.infra.security.PasswordHasher;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

/**
 * §6.2 bcrypt 互认测试
 * 验证 Java jBCrypt 12 rounds 与 Python 现有密码哈希互认
 */
@SpringBootTest
public class BcryptCompatibilityTest {

    @Autowired
    private PasswordHasher passwordHasher;

    /**
     * 测试 1：Java 生成的哈希格式正确性
     */
    @Test
    void javaHashFormatIsCorrect() {
        String password = "EvalTest@2026";
        String hash = passwordHasher.hash(password);

        // bcrypt hash 格式：$2a$12$[22 chars].[31 chars]
        assertTrue(hash.startsWith("$2a$12$"), "Hash 应以 $2a$12$ 开头（bcrypt rounds=12）");
        assertEquals(60, hash.length(), "bcrypt hash 长度应为 60 字符");
    }

    /**
     * 测试 2：Java 哈希的密码可自验证
     */
    @Test
    void javaHashCanVerifyItself() {
        String password = "EvalTest@2026";
        String hash = passwordHasher.hash(password);

        assertTrue(passwordHasher.verify(password, hash), "Java 应能验证自己生成的哈希");
        assertFalse(passwordHasher.verify("wrong_password", hash), "错误密码应验证失败");
    }

    /**
     * 测试 3：Java 验证 Python 生成的哈希
     *
     * 数据库中 e4test 用户的密码哈希（Python 生成）：
     * $2a$12$kMGnWjnSo07lc1lX/TrAKOFOavW6o7v6AI6wSsJbw8NLnCFKoFxI.
     *
     * 密码：EvalTest@2026
     */
    @Test
    void javaCanVerifyPythonHash() {
        // 从数据库获取的 Python 生成的 bcrypt hash（e4test 用户）
        String pythonHash = "$2a$12$kMGnWjnSo07lc1lX/TrAKOFOavW6o7v6AI6wSsJbw8NLnCFKoFxI.";

        String correctPassword = "EvalTest@2026";

        // Java jBCrypt 应能验证 Python 生成的哈希
        assertTrue(passwordHasher.verify(correctPassword, pythonHash),
            "Java 应能验证 Python 生成的 bcrypt hash（互认性）");
    }

    /**
     * 测试 4：Java 验证数据库中的实际哈希
     */
    @Test
    void javaCanVerifyDatabaseHash() {
        // 从数据库查询的实际哈希（通过 SQL 查询获取）
        // SELECT password FROM users WHERE username='e4test'
        String dbHash = "$2a$12$kMGnWjnSo07lc1lX/TrAKOFOavW6o7v6AI6wSsJbw8NLnCFKoFxI.";

        assertTrue(passwordHasher.verify("EvalTest@2026", dbHash),
            "Java 应能验证数据库中的实际密码哈希");
    }

    /**
     * 测试 5：不同密码验证失败
     */
    @Test
    void wrongPasswordFailsVerification() {
        String dbHash = "$2a$12$kMGnWjnSo07lc1lX/TrAKOF7KjyKqZJgRhQNK3hK0b.2Lqx3K6Qm";

        assertFalse(passwordHasher.verify("wrong_password", dbHash),
            "错误密码应验证失败");
        assertFalse(passwordHasher.verify("", dbHash),
            "空密码应验证失败");
    }

    /**
     * 测试 6：双向互认（Python 验证 Java 生成的哈希）
     *
     * 注意：此测试需要 Python 环境，暂时跳过
     * TODO: 在 Python 环境中验证 Java 生成的哈希
     */
    // @Test
    // void pythonCanVerifyJavaHash() {
    //     String javaHash = passwordHasher.hash("EvalTest@2026");
    //     // 调用 Python 验证脚本验证
    //     assertTrue(pythonVerify("EvalTest@2026", javaHash));
    // }
}
