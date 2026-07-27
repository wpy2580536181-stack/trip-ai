-- 启用 pgvector 向量检索扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用 pg_trgm 三元组扩展（加速 LIKE 模糊检索）
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 创建中文全文检索配置（使用 simple 字典，无 zhparser 时的基本方案）
-- 若后续安装 zhparser，可替换为: CREATE TEXT SEARCH CONFIGURATION chinese (PARSER = zhparser);
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'chinese') THEN
    CREATE TEXT SEARCH CONFIGURATION chinese (COPY = simple);
  END IF;
END
$$;
