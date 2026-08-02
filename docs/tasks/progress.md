# 任务追踪

## 当前进度

| 阶段 | 状态 | 提交 | 测试 |
|------|------|------|------|
| A1-A4 工程基建 | ✅ 完成 | ✅ | ⚠️ 部分 |
| B1-B7 用户/CRUD | ✅ 完成 | ✅ | ⚠️ 部分 |
| C0 TaskQueue | ✅ 完成 | ✅ | ⚠️ |
| C1 Embedder/Reranker | ✅ 完成 | ✅ | ⚠️ |
| D1 LLM Gateway | ✅ 完成 | ✅ | ⚠️ |
| D2 Token 记账 | ✅ 完成 | ✅ | ⚠️ |
| D3 SSE 基建 | ✅ 完成 | ✅ | ⚠️ |
| **D4 ChatController** | ✅ **完成** | ✅ | ✅ **已创建** |
| **D5 工具层** | ✅ **完成** | ✅ | ✅ **已创建** |
| **D6 高德 MCP** | ✅ **完成** | ✅ | ✅ **已创建** |
| **C2 检索流水线** | ✅ **完成** | ✅ | ✅ **已创建** |

## 测试覆盖

### D4 测试（3 个文件）
- ✅ EventSinkTest
- ✅ MessagePersistenceServiceTest
- ✅ ChatControllerTest

### D5 测试（3 个文件）
- ✅ CircuitBreakerTest（已实现）
- ✅ ToolResilienceWrapperTest
- ✅ ToolContractTest

### D6 测试（3 个文件）
- ✅ McpSmokeTest
- ✅ McpGuardsTest
- ✅ McpStatsTest

### C2 测试（5 个文件）
- ✅ QueryRewriterTest（关键词提取 + 城市检测 + 意图识别）
- ✅ RrfTest（RRF 合并 + 加权 RRF + 空输入 + 单路径）
- ✅ RatingSearchTest（骨架）
- ✅ FulltextSearchTest（骨架）
- ✅ RetrievalPipelineTest（骨架）

## 验收标准

### D4
- 3.2 chat SSE 端点 12 类事件
- 3.5 消息落库 3s flush
- 3.6 标题截断 + 非旅行短路

### D5
- 4.3 工具层 10 业务工具 + 韧性 + 缓存

### D6
- 6.3 MCP 客户端 + guards + mcp-stats
- 4.3(MCP 部分)

### C2
- 5.1(双路)
- 5.2
- 5.6(部分)

## 下一步

- [ ] **C3 四路召回 + credibility 重排**
- [ ] C4 embedding_sync
- [ ] C4 embedding_sync
- [ ] D7 Orchestrator + Research/Planner/Review
- [ ] D8 ChatAgent 双流 + 四升级工具
- [ ] D9 技能系统 + patch_engine
- [ ] D10 并发/预算守卫流式挂载
- [ ] D11 recommend 链路
- [ ] D12 post_chat_followup
- [ ] E1-E5 运维面

## 待优化

- D4/D5 测试需要补充更多断言逻辑
- 所有测试需要实际运行验证通过
- A/B/C/D1-3 阶段也需要补充测试
