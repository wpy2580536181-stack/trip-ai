-- 修复 P2-8：知识库搜索 LIKE 全表扫描
-- 给 spots 表的 name + description 加 FULLTEXT 索引
-- 适用：MySQL 5.6+ / InnoDB

-- 1. 添加 FULLTEXT 联合索引
ALTER TABLE spots ADD FULLTEXT INDEX ft_name_desc (name, description);

-- 2. 验证
SHOW INDEX FROM spots WHERE Key_name = 'ft_name_desc';

-- 3. 测试查询
-- SELECT name, description FROM spots
-- WHERE MATCH(name, description) AGAINST('宽窄巷子' IN NATURAL LANGUAGE MODE)
-- LIMIT 10;

-- 注意：FULLTEXT 索引不记录到 Prisma schema，
-- 重新跑 prisma db push 不会删除这个索引（Prisma 不识别会保留）。
-- 如需重建，注释掉这行 SQL 后执行即可。
