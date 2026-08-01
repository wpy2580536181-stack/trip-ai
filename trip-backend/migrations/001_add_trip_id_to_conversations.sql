-- migrations/001_add_trip_id_to_conversations.sql
-- 为 conversations 表添加 trip_id 字段，建立与 trips 表的关联

-- 1. 添加 trip_id 列（幂等保护）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'conversations' AND column_name = 'trip_id'
    ) THEN
        ALTER TABLE conversations ADD COLUMN trip_id INTEGER;
    END IF;
END $$;

-- 2. 添加外键约束（幂等保护）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'conversations' AND constraint_name = 'fk_conversations_trip_id'
    ) THEN
        ALTER TABLE conversations 
        ADD CONSTRAINT fk_conversations_trip_id 
        FOREIGN KEY (trip_id) REFERENCES trips(id) 
        ON DELETE SET NULL;
    END IF;
END $$;

-- 3. 添加索引（幂等保护）
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'conversations' AND indexname = 'idx_conversations_trip_id'
    ) THEN
        CREATE INDEX idx_conversations_trip_id 
        ON conversations(trip_id);
    END IF;
END $$;

-- 4. 验证：查询列信息
SELECT 
    column_name, 
    data_type, 
    is_nullable 
FROM information_schema.columns 
WHERE table_name = 'conversations' 
  AND column_name = 'trip_id';

-- 5. 验证：查询外键信息
SELECT
    conname AS constraint_name,
    pg_get_constraintdef(c.oid) AS constraint_definition
FROM pg_constraint c
JOIN pg_namespace n ON n.oid = c.connamespace
WHERE conrelid = 'conversations'::regclass
  AND conname = 'fk_conversations_trip_id';

-- 6. 验证：查询索引信息
SELECT
    indexname AS index_name,
    indexdef AS index_definition
FROM pg_indexes
WHERE tablename = 'conversations'
  AND indexname = 'idx_conversations_trip_id';

-- 7. 验证：查询存量数据（trip_id 应为 NULL）
SELECT 
    COUNT(*) AS total_conversations,
    COUNT(CASE WHEN trip_id IS NULL THEN 1 END) AS with_null_trip_id,
    COUNT(CASE WHEN trip_id IS NOT NULL THEN 1 END) AS with_trip_id
FROM conversations;
