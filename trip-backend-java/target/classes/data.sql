-- 默认角色数据（启动时自动插入）

-- USER 角色
INSERT INTO roles (id, name)
SELECT 2, 'USER'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'USER');

-- ADMIN 角色
INSERT INTO roles (id, name)
SELECT 1, 'ADMIN'
WHERE NOT EXISTS (SELECT 1 FROM roles WHERE name = 'ADMIN');
