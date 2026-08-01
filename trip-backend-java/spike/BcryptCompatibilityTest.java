package com.trip.backend.spike;

import org.mindrot.jbcrypt.BCrypt;

/**
 * bcrypt 互认测试
 *
 * 验证 Java jBCrypt (rounds=12) 能否识别 Python bcrypt 生成的密码哈希
 */
public class BcryptCompatibilityTest {

    public static void main(String[] args) {
        System.out.println("=".repeat(60));
        System.out.println("bcrypt 互认测试");
        System.out.println("=".repeat(60));

        // 测试密码
        String password = "test123";

        // Java 生成哈希（rounds=12）
        System.out.println("\n[1] Java 生成哈希（rounds=12）");
        String javaHash = BCrypt.hashpw(password, BCrypt.gensalt(12));
        System.out.println("哈希: " + javaHash);

        // 验证 Java 哈希
        System.out.println("\n[2] Java 验证 Java 生成的哈希");
        boolean javaVerify = BCrypt.checkpw(password, javaHash);
        System.out.println("结果: " + (javaVerify ? "✅ 成功" : "❌ 失败"));

        // 测试 Python 生成的哈希（如果提供了）
        String pythonHash = System.getenv().getOrDefault("PYTHON_BCRYPT_HASH", "");
        if (!pythonHash.isEmpty()) {
            System.out.println("\n[3] Java 验证 Python 生成的哈希");
            System.out.println("Python 哈希: " + pythonHash);
            boolean pythonVerify = BCrypt.checkpw(password, pythonHash);
            System.out.println("结果: " + (pythonVerify ? "✅ 成功" : "❌ 失败"));

            if (pythonVerify) {
                System.out.println("\n✅ bcrypt 互认验证通过（Java 可识别 Python 哈希）");
            } else {
                System.out.println("\n❌ bcrypt 互认验证失败（请检查 rounds 是否一致）");
            }
        } else {
            System.out.println("\n[3] 跳过 Python 哈希验证");
            System.out.println("提示：如需验证 Python 生成的哈希，设置环境变量 PYTHON_BCRYPT_HASH");
        }

        // 测试不同 rounds 的兼容性
        System.out.println("\n[4] 测试不同 rounds 的兼容性");
        for (int rounds = 4; rounds <= 12; rounds += 2) {
            String hash = BCrypt.hashpw(password, BCrypt.gensalt(rounds));
            boolean verify = BCrypt.checkpw(password, hash);
            System.out.printf("rounds=%2d: %s%n", rounds, verify ? "✅" : "❌");
        }

        System.out.println("\n" + "=".repeat(60));
        System.out.println("测试完成");
        System.out.println("=".repeat(60));

        // 生成一个测试用的哈希，供 Python 侧验证
        System.out.println("\n[供 Python 侧验证] Java 生成的哈希:");
        System.out.println("echo '" + javaHash + "'");
    }
}
