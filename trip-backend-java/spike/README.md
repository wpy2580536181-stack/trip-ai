# LLM Spike Tests

验证 langchain4j 1.x 关键能力的独立测试项目。

## 测试目标

1. **流式 tool_calls delta 累积** — 验证能否在流式过程中逐步累积完整工具调用
2. **末帧 usage 提取** — 验证 `include_usage` + `cachedTokens` 能否取出
3. **中文 tool schema** — 验证 description 字段中文是否正常下发

## 前置条件

```bash
# 设置环境变量
export DEEPSEEK_API_KEY="your-api-key"

# （可选）设置 Python bcrypt 哈希用于互认测试
export PYTHON_BCRYPT_HASH="$2a$12$..."
```

## 运行

```bash
# 编译并运行
mvn compile exec:java -Dexec.mainClass="com.trip.backend.spike.LlmSpikeTest"

# 或仅编译后运行
mvn compile
java -cp target/classes:target/dependency/* com.trip.backend.spike.LlmSpikeTest
```

## 预期输出

```
============================================================
LLM Spike Test - langchain4j 1.x
============================================================

[测试 1] 非流式调用 + 工具定义
✅ 工具调用成功: 1 个

[测试 2] 流式调用 + tool_calls delta 累积
✅ 流式 tool_calls 累积成功（长度=XXX）

[测试 3] usage 提取（含 cachedTokens）
✅ Token 使用统计正常
✅ cachedTokens 提取成功（如 API 返回）

[测试 4] 中文 tool schema 下发
✅ 中文 tool schema 调用成功

============================================================
✅ 所有测试完成
============================================================
```

## 验收标准

- [ ] 测试 1: 工具调用成功（至少 1 个 tool_call）
- [ ] 测试 2: 流式 tool_calls delta 累积成功（长度 > 0）
- [ ] 测试 3: Token 使用统计正常；cachedTokens 字段存在（如 API 支持）
- [ ] 测试 4: 中文 tool schema 调用成功

## 风险预案

如果 spike 失败：
- **tool_calls delta 累积不全** → 降级自研 OpenAI 协议层（见技术方案 T2）
- **usage/cachedTokens 取不到** → 降级自研 OpenAI 协议层
- **中文 description 下发异常** → 降级英文或手动编码 schema
