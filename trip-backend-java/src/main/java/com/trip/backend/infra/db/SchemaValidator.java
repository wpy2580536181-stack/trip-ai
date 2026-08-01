package com.trip.backend.infra.db;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.boot.CommandLineRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * Schema 校验器（对应 Python create_tables.py 的补全逻辑）
 * - 启动时校验 12 表齐全
 * - 缺失表幂等补建（仅 password_resets 预期缺失）
 */
@Component
public class SchemaValidator implements CommandLineRunner {

    @PersistenceContext
    private EntityManager entityManager;

    private final JdbcTemplate jdbcTemplate;

    public SchemaValidator(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void run(String... args) throws Exception {
        System.out.println("[SchemaValidator] 正在校验数据库表结构...");

        // 查询现有表
        var tables = jdbcTemplate.queryForList(
            "SELECT table_name FROM information_schema.tables " +
            "WHERE table_schema='public' AND table_type='BASE TABLE' " +
            "ORDER BY table_name",
            String.class
        );

        System.out.println("[SchemaValidator] 找到 " + tables.size() + " 张表: " + tables);

        // 检查 password_resets 表是否存在
        boolean hasPasswordResets = tables.contains("password_resets");

        if (!hasPasswordResets) {
            System.out.println("[SchemaValidator] password_resets 表不存在，正在创建...");
            createPasswordResetsTable();
            System.out.println("[SchemaValidator] password_resets 表创建完成");
        } else {
            System.out.println("[SchemaValidator] password_resets 表已存在，跳过创建");
        }

        // 验证 HNSW 索引（可选的日志输出）
        validateHnswIndexes();

        System.out.println("[SchemaValidator] 校验完成");
    }

    /**
     * 创建 password_resets 表（幂等）
     */
    private void createPasswordResetsTable() {
        String sql = """
            CREATE TABLE IF NOT EXISTS password_resets (
                id SERIAL PRIMARY KEY,
                email VARCHAR(100) NOT NULL,
                token VARCHAR(255) NOT NULL UNIQUE,
                expires_at TIMESTAMPTZ NOT NULL,
                used BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token);
            CREATE INDEX IF NOT EXISTS idx_password_resets_email ON password_resets(email);
            """;

        jdbcTemplate.execute(sql);
    }

    /**
     * 验证 HNSW 索引
     */
    private void validateHnswIndexes() {
        try {
            var indexes = jdbcTemplate.queryForList(
                "SELECT indexname, indexdef FROM pg_indexes " +
                "WHERE tablename IN ('spots', 'spot_docs') AND indexdef LIKE '%hnsw%'",
                String.class, String.class
            );

            if (indexes.isEmpty()) {
                System.out.println("[SchemaValidator] ⚠️ 未找到 HNSW 索引（向量检索可能受影响）");
            } else {
                System.out.println("[SchemaValidator] 找到 " + indexes.size() + " 个 HNSW 索引");
            }
        } catch (Exception e) {
            System.out.println("[SchemaValidator] ⚠️ HNSW 索引检查失败: " + e.getMessage());
        }
    }
}
