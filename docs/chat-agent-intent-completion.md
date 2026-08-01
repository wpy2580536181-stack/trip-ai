# ChatAgent 需求补全（Intent Completion）

> 实现日期：2026-08-01  
> 关联 PRD：`tasks/chat-agent-intent-completion-prd.md`  
> 关联 Tech Spec：`tasks/chat-agent-intent-completion-tech-spec.md`  
> 关联 Plan：`tasks/chat-agent-intent-completion-plan.md`

---

## 概述

当用户输入不完整（缺少目的地、天数或预算）时，ChatAgent 不再使用默认值直接生成行程，而是通过 **ClarifyCard** 追问缺失字段，收集齐后再进入 Orchestrator 规划流程。

对标竞品：KINLIK041/meituan 的 `NeedCompletionCard` 模式。

---

## 触发条件

`check_completeness(args)` 检查以下字段：

| 字段 | 必填 | 说明 |
|------|------|------|
| `city` | ✅ | 目的地城市（可从历史对话继承） |
| `days` | ✅ | 游玩天数（不可继承，必须用户明确） |
| `budget` | ✅ | 预算（不可继承，必须用户明确） |
| `departure_city` | ❌ | 出发城市（可选，不影响完整性） |

---

## 用户流程

```
用户：周末想出去逛逛
    ↓
ChatAgent → _escalate_plan()
    ↓
check_completeness() → missing = ["city", "days", "budget"]
    ↓
SSE event: {type: "card", card_type: "clarify", data: {fields: [...]}}
    ↓
前端展示 ClarifyCard（下拉选择城市/天数/预算范围）
    ↓
用户填写并提交 → 格式化为结构化消息重新发送
    ↓
check_completeness() → missing = []
    ↓
Orchestrator.plan() → 生成行程
```

---

## 数据结构

### SSE 事件

```json
{
  "type": "card",
  "card_type": "clarify",
  "data": {
    "fields": [
      {
        "key": "city",
        "label": "目的地",
        "field_type": "select",
        "required": true,
        "options": ["北京", "上海", "广州", "深圳", ...],
        "placeholder": "请输入或选择城市"
      },
      {
        "key": "days",
        "label": "天数",
        "field_type": "select",
        "required": true,
        "options": ["1天", "2天", "3天", "4天", "5天", "6天", "7天"]
      },
      {
        "key": "budget",
        "label": "预算（元）",
        "field_type": "select",
        "required": true,
        "options": ["1000以下", "1000-3000", "3000-5000", "5000-10000", "10000以上"]
      }
    ],
    "title": "请补充以下信息",
    "submit_label": "开始规划",
    "cancel_label": "取消"
  }
}
```

---

## 改动文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `trip-backend/src/services/agent/intent.py` | 新增 `ClarifyField`/`ClarifyCardData`/`check_completeness()`/`_build_clarify_field()` | 后端数据模型 + 完整性检查 |
| `trip-backend/tests/test_intent_completion.py` | 新建，14 个单元测试 | `check_completeness` + `_build_clarify_field` |
| `trip-backend/src/services/agent/agents/chat_agent.py` | `_escalate_plan()` 前置拦截 | 缺失时发出 clarify card |
| `trip-backend/tests/test_clarify_integration.py` | 新建，10 个集成测试 | 端到端流程验证 |
| `trip-front/src/components/ClarifyCard.vue` | 新建 | 前端表单组件 |
| `trip-front/src/components/ChatPanel.vue` | 新增 `clarifyCards` + `handleClarifySubmit()` | 集成到对话面板 |

---

## 验收标准

- AC-01：输入"周末想出去逛逛" → 返回 clarify 卡片（不直接生成行程）
- AC-02：缺城市 → 追问"请问您想去哪个城市呢？"
- AC-03：缺天数 → 追问"计划玩几天？"
- AC-04：缺预算 → 追问"预算大概多少？"
- AC-05：完整输入"去成都玩3天，预算4000" → 直接规划，无 clarify 卡片
- AC-06：补全后提交 → 自动触发规划，无需二次发送
- AC-07：历史有城市 → 城市继承，只追问缺失字段
- AC-08：非规划请求 → 不触发补全逻辑

---

## 测试覆盖

```bash
cd trip-backend && .venv/bin/python -m pytest tests/test_intent_completion.py tests/test_clarify_integration.py -v
```

当前测试数：**24 tests**（14 intent + 10 integration）

---

## 不变动范围

- `orchestrator.py` / `planner_agent.py` / `research_agent.py` — 核心规划链路
- `agent_engine.py:chat()` — 统一入口层
- `review.py` / `trip_service.py` — 与补全逻辑无关

---

## 后续迭代

- [ ] 叠加方案 B：`ChatAgent.run()` 后置拦截（兜底 LLM 未触发 `trigger_plan` 的场景）
- [ ] 结构化偏好提取：从对话历史提取 `travel_style` / `budget_level`
- [ ] 多轮追问降级：第 1 轮后仍缺失 → 开放规划（LLM 自行处理）
