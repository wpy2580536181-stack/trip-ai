#!/usr/bin/env python3
"""前置调查：查询现有 PostgreSQL 数据库状态"""

import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = "postgresql+asyncpg://trip:trip123@localhost:5432/trip_db"

async def main():
    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.connect() as conn:
        print("=" * 60)
        print("1. 查询所有表（确认 12 表）")
        print("=" * 60)
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_type='BASE TABLE'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]
        print(f"找到 {len(tables)} 张表：")
        for t in tables:
            print(f"  - {t}")

        print("\n" + "=" * 60)
        print("2. 验证 password_resets 表状态")
        print("=" * 60)
        result = await conn.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name='password_resets'
            ORDER BY ordinal_position
        """))
        columns = result.fetchall()
        if columns:
            print("password_resets 表已存在，字段列表：")
            for col in columns:
                print(f"  - {col[0]} ({col[1]}, nullable={col[2]})")
        else:
            print("password_resets 表不存在（需要补建）")

        print("\n" + "=" * 60)
        print("3. 验证 HNSW 索引参数")
        print("=" * 60)
        result = await conn.execute(text("""
            SELECT indexname, indexdef FROM pg_indexes
            WHERE tablename IN ('spots', 'spot_docs')
            AND indexdef LIKE '%hnsw%'
            ORDER BY tablename, indexname
        """))
        indexes = result.fetchall()
        if indexes:
            print("找到 HNSW 索引：")
            for idx in indexes:
                print(f"  - {idx[0]}:")
                print(f"    {idx[1]}")
        else:
            print("未找到 HNSW 索引")

        print("\n" + "=" * 60)
        print("4. 抽样向量数据（用于 cosine 一致性回归）")
        print("=" * 60)
        result = await conn.execute(text("""
            SELECT id, name, LEFT(embedding::text, 100) AS embedding_preview
            FROM spots
            WHERE embedding IS NOT NULL
            LIMIT 3
        """))
        rows = result.fetchall()
        if rows:
            print(f"抽样 {len(rows)} 条 spots.embedding：")
            for row in rows:
                print(f"  - id={row[0]}, name={row[1]}")
                print(f"    embedding[:100]={row[2]}...")
        else:
            print("spots 表中无 embedding 数据")

        print("\n" + "=" * 60)
        print("5. 验证现有数据量")
        print("=" * 60)
        tables_to_count = ['users', 'spots', 'trips', 'conversations', 'messages',
                          'spot_docs', 'feedbacks', 'roles', 'password_resets',
                          'agent_steps', 'token_usage_logs']
        for tbl in tables_to_count:
            result = await conn.execute(text(f'SELECT COUNT(*) FROM {tbl}'))
            count = result.scalar()
            print(f"  {tbl}: {count} 行")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
