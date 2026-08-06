-- 测试数据清理脚本（每个测试方法后执行）
-- 清理所有业务数据，保留 schema

DELETE FROM feedbacks;
DELETE FROM messages;
DELETE FROM conversations;
DELETE FROM trips;
DELETE FROM password_resets;
DELETE FROM agent_steps;
DELETE FROM token_usage_logs;
DELETE FROM spots;
DELETE FROM spot_docs;
DELETE FROM users;
DELETE FROM roles;

-- 重新插入基础角色数据
INSERT INTO roles (id, name) VALUES (1, 'ADMIN'), (2, 'USER')
ON CONFLICT (id) DO NOTHING;
