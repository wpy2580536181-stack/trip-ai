# E4 端到端联调实施计划

> **时间**：2026-08-02
> **目标**：验证 Java 后端功能对等性 + 前端零改动可用

## 验收条目对照（PRD §7）

| 验收条目 | 验证方式 | 状态 |
|---------|---------|------|
| **7.1** 前端零改动全流程走通 | 前端切换 VITE_API_TARGET=Java 服务，跑通全部页面 | ⏳ |
| **7.2** eval fixture 通过率 ≥ 基线 | 双端跑同一 eval 集对比 | ⏳ |
| **7.3** 性能不劣于基线（QPS/SSE 时长） | 压测脚本验证 | ⏳（E3） |
| **7.4** 全部阶段 1-6 测试 CI 全绿 | CI 流水线 | ⏳（E5） |

## Python e2e 测试清单（6 个流程）

1. **test_auth_flow.py** - 注册/登录/token/改密/忘记密码（11 个测试）
2. **test_conversation_flow.py** - 会话创建/列表/详情/删除（6 个测试）
3. **test_trip_planning.py** - 行程规划/recommend/chat（8 个测试）
4. **test_feedback_flow.py** - 反馈评分/列表/统计（5 个测试）
5. **test_knowledge_flow.py** - 知识库 CRUD/spot-docs（6 个测试）
6. **test_error_scenarios.py** - 错误场景/权限/IDOR（7 个测试）

**总计**：43 个 e2e 测试用例

## 实施步骤

### 步骤 1：启动 Java 后端

- 检查 PostgreSQL + Redis 可用性
- 启动 Spring Boot（端口 8000）
- 等待健康检查就绪

### 步骤 2：用 Python 测试脚本验证 Java 后端

**目标**：复用 Python e2e 测试套件，仅修改 base_url 指向 Java 后端

**方法**：
- 写一个 Python 脚本（`run_e2e_against_java.py`）
- 复用 `tests/e2e/conftest.py` 的 fixture 结构
- 仅修改 `backend_server` fixture 的启动命令（不启动 Python 后端，直接等待 Java 后端就绪）
- 运行所有 6 个测试文件

**预期**：全部测试通过（或仅有已知差异项）

### 步骤 3：手动验证前端全流程

- 修改前端 `.env` 或环境变量 `VITE_API_TARGET=http://localhost:8000`
- 启动前端（`npm run dev`）
- 手动执行关键流程：
  1. 注册/登录
  2. 发起聊天（SSE 流验证）
  3. 行程规划（recommend-stream 验证）
  4. 历史会话查看
  5. 知识库管理（Admin）
  6. 反馈评分
  7. Token 用量统计

### 步骤 4：eval 双回归验证（5.2/5.8）

- 查找 Python eval 脚本/数据集
- 对 Java 后端发起 eval 请求
- 对比 Hit@K/MRR 指标

## 当前阻塞项

- [ ] PostgreSQL 是否运行（`pg_isready` 检查）
- [ ] Redis 是否运行（`redis-cli ping` 检查）
- [ ] Java 后端首次启动是否成功
- [ ] eval 数据集位置与格式

## 开始执行
