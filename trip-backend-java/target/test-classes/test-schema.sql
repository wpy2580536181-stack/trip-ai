-- 测试 Schema（从实际 schema 简化）
-- 用于集成测试，自动创建所有必要的表

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    nickname VARCHAR(50),
    avatar VARCHAR(255),
    phone VARCHAR(20),
    bio VARCHAR(255),
    role_id INTEGER NOT NULL REFERENCES roles(id),
    status INTEGER NOT NULL DEFAULT 1,
    preferences JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS password_resets (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    from_city VARCHAR(100),
    city VARCHAR(100) NOT NULL,
    days INTEGER NOT NULL,
    budget INTEGER NOT NULL,
    content JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'completed',
    parent_trip_id BIGINT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trip_id BIGINT REFERENCES trips(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    tool_calls JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_steps (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL,
    tool_name VARCHAR(100),
    input_text TEXT,
    output_text TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS token_usage_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    request_type VARCHAR(50) NOT NULL,
    route VARCHAR(100),
    conversation_id BIGINT REFERENCES conversations(id) ON DELETE SET NULL,
    message_id BIGINT REFERENCES messages(id) ON DELETE SET NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    cached_tokens INTEGER,
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS spots (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    city VARCHAR(100) NOT NULL,
    category VARCHAR(100) NOT NULL,
    description TEXT,
    tags JSONB,
    avg_cost INTEGER,
    duration INTEGER,
    open_time VARCHAR(100),
    rating DOUBLE PRECISION,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS spot_docs (
    id BIGSERIAL PRIMARY KEY,
    spot_id BIGINT NOT NULL REFERENCES spots(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(384),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE IF NOT EXISTS feedbacks (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id BIGINT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    rating INTEGER NOT NULL,
    comment TEXT,
    tags JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_trips_user_id ON trips(user_id);
CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_spots_city_category ON spots(city, category);
CREATE INDEX IF NOT EXISTS idx_token_usage_user_created ON token_usage_logs(user_id, created_at);
