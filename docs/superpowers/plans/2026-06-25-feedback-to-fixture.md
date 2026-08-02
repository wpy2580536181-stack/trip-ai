# Feedback → Fixture 自动化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 半自动把"在线负反馈"转成"回归测试 fixture 骨架"——admin 补 expected → 真实用户踩过的坑变 CI 测试。

**Architecture:** CLI 脚本 + API 端点 + 前端按钮，3 入口都走同一 `feedbackService.convertToFixture()`。输出到 `eval/fixtures/generated/`，与手写 `trip-planning/` 目录分离。runner 扫 `fixtures/**/*.yaml` 兼容双目录。

**Tech Stack:** Node.js + Prisma + js-yaml + Express + Vue 3 / Vant + Vitest

---

## 文件结构

```
trip-server/
├── scripts/
│   └── feedback-to-fixture.ts                 # NEW CLI
├── src/
│   ├── services/
│   │   ├── feedbackService.ts                 # +convertToFixture()
│   │   └── fixtureConverter.ts                # NEW YAML 序列化
│   ├── controllers/
│   │   └── feedback.controller.ts             # +convertToFixture()
│   ├── routes/
│   │   └── feedback.routes.ts                 # +POST /admin/convert-to-fixture
│   └── services/__tests__/
│       ├── feedbackService.test.ts            # +2 测试
│       └── fixtureConverter.test.ts           # NEW 单元测试
├── eval/
│   ├── runner.ts                              # 改扫 fixtures/**/*.yaml
│   └── fixtures/
│       └── generated/                         # NEW 目录
│           └── .gitkeep
trip-front/
└── src/
    ├── api/feedback.ts                        # +convertToFixture()
    └── views/
        └── AdminFeedbackDashboard.vue         # +按钮 + modal
docs/
├── feedback-to-fixture.md                     # NEW 使用文档
└── feedback-dashboard.md                      # UPDATE 链入
```

---

## Task 1: 装 js-yaml + 生成 generated 目录

**Files:**
- Modify: `trip-server/package.json`
- Create: `trip-server/eval/fixtures/generated/.gitkeep`

- [ ] **Step 1: 装 js-yaml**

```bash
cd trip-server
pnpm add js-yaml @types/js-yaml
```

- [ ] **Step 2: 验证装好**

```bash
cd trip-server && node -e "const y=require('js-yaml');console.log(y.dump({a:1}))"
```
Expected: `a: 1\n`

- [ ] **Step 3: 创建 generated 目录**

```bash
mkdir -p trip-server/eval/fixtures/generated
touch trip-server/eval/fixtures/generated/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add trip-server/package.json trip-server/eval/fixtures/generated/.gitkeep
git commit -m "chore: add js-yaml + created eval/fixtures/generated/ for feedback-imported fixtures"
```

---

## Task 2: fixtureConverter.ts 核心序列化

**Files:**
- Create: `trip-server/src/services/fixtureConverter.ts`
- Create: `trip-server/src/services/__tests__/fixtureConverter.test.ts`

- [ ] **Step 1: 写 fixtureConverter.ts**

```typescript
/**
 * Fixture 转换器
 *
 * 把"在线负反馈"序列化成 eval fixture YAML 骨架。
 * admin 收到后手动补 expected 段（must_contain_keywords 等）。
 *
 * 关键设计：
 * - input.message 选 < targetMessageId 的最后 user turn（不是 assistant 自身）
 * - history 包含 target message 之前的所有轮次（user + assistant）
 * - content 截断 10KB 防止 fixture 膨胀
 * - id slugify 兼容中文/英文/数字
 * - yaml.dump 写死 defaultStringAsSuperLiteral 字段名稳定
 */

import yaml from 'js-yaml'

const MAX_CONTENT_LENGTH = 10000

export interface ConvertInput {
  feedbackId: number
  feedbackComment: string | null
  feedbackTags: string[] | null
  feedbackCreatedAt: Date
  messageId: number
  messageContent: string
  userId: number
  username: string
  userPreferences: Record<string, any> | null
  /** 整段 conversation 的 messages（含 user/assistant），按 createdAt 升序 */
  conversationMessages: Array<{
    id: number
    role: 'user' | 'assistant'
    content: string
    createdAt: Date
  }>
}

export function slugify(text: string): string {
  return text
    .slice(0, 30)
    .replace(/[^\w\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase() || 'untitled'
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + '...[已截断]'
}

/**
 * 选 input.message：< targetMessageId 的最后 user turn
 */
function pickInputMessage(
  msgs: ConvertInput['conversationMessages'],
  targetId: number
): string {
  const earlier = msgs.filter((m) => m.id < targetId)
  const lastUser = [...earlier].reverse().find((m) => m.role === 'user')
  return lastUser?.content ?? ''
}

/**
 * 组 history：< targetMessageId 的所有轮次（user+assistant）
 */
function pickHistory(
  msgs: ConvertInput['conversationMessages'],
  targetId: number
): Array<{ role: 'user' | 'assistant'; content: string }> {
  return msgs
    .filter((m) => m.id < targetId)
    .map((m) => ({ role: m.role, content: truncate(m.content, MAX_CONTENT_LENGTH) }))
}

export function toYAML(input: ConvertInput): string {
  const inputMessage = truncate(pickInputMessage(input.conversationMessages, input.messageId), MAX_CONTENT_LENGTH)
  const history = pickHistory(input.conversationMessages, input.messageId)
  const userSlug = slugify(input.username).slice(0, 20)
  const msgSlug = slugify(inputMessage).slice(0, 30)

  const fixture: Record<string, any> = {
    id: `feedback-${input.feedbackId}-${userSlug}-${msgSlug}`,
    description: `来自生产反馈 #${input.feedbackId}：${input.feedbackComment?.slice(0, 50) || '(无评论)'}`,
    tags: ['feedback-imported', 'user-reported', ...(input.feedbackTags || [])],
    source: {
      feedback_id: input.feedbackId,
      message_id: input.messageId,
      user: input.username,
      created_at: input.feedbackCreatedAt.toISOString(),
      original_comment: input.feedbackComment || null,
    },
    input: {
      message: inputMessage,
      preferences: input.userPreferences || {},
      history,
    },
    expected: {
      must_contain_keywords: [],
      must_not_contain_keywords: [],
    },
    evaluators: ['schema_check', 'keyword_coverage'],
  }

  return yaml.dump(fixture, {
    lineWidth: 120,
    noRefs: true,
    quotingType: '"',
  })
}
```

- [ ] **Step 2: 写单元测试 fixtureConverter.test.ts**

```typescript
import { describe, it, expect } from 'vitest'
import { toYAML, slugify, ConvertInput } from '../fixtureConverter'
import yaml from 'js-yaml'

const baseInput: ConvertInput = {
  feedbackId: 113,
  feedbackComment: '推荐不准',
  feedbackTags: ['recommend'],
  feedbackCreatedAt: new Date('2026-06-24T10:00:00Z'),
  messageId: 847,
  messageContent: 'agent 的回复...',  // assistant 内容
  userId: 5,
  username: 'eval-test',
  userPreferences: { travelStyle: 'relaxed', interests: ['美食'] },
  conversationMessages: [
    { id: 845, role: 'user', content: '上海 2 天推荐几个好吃的', createdAt: new Date() },
    { id: 846, role: 'assistant', content: '好的，为您推荐...', createdAt: new Date() },
    { id: 847, role: 'user', content: '加点辣的', createdAt: new Date() },  // target 之前最后 user
    { id: 848, role: 'assistant', content: 'agent 这次回复', createdAt: new Date() },  // target
  ],
}

describe('slugify', () => {
  it('处理中文 + 英文 + 数字', () => {
    expect(slugify('上海 2 天 推荐!')).toBe('上海-2-天-推荐')
  })

  it('空字符串返回 untitled', () => {
    expect(slugify('')).toBe('untitled')
    expect(slugify('!!!')).toBe('untitled')
  })

  it('截断到 30 字符', () => {
    const long = 'a'.repeat(50)
    expect(slugify(long).length).toBeLessThanOrEqual(30)
  })
})

describe('toYAML - input.message 选择', () => {
  it('选 < messageId 的最后 user turn', () => {
    const yamlStr = toYAML(baseInput)
    const parsed = yaml.load(yamlStr) as any
    expect(parsed.input.message).toBe('加点辣的')
  })

  it('没有 user turn 时 message 为空', () => {
    const input = {
      ...baseInput,
      conversationMessages: [
        { id: 845, role: 'assistant' as const, content: '...', createdAt: new Date() },
        { id: 848, role: 'assistant' as const, content: 'agent 这次回复', createdAt: new Date() },
      ],
    }
    const parsed = yaml.load(toYAML(input)) as any
    expect(parsed.input.message).toBe('')
  })
})

describe('toYAML - history 过滤', () => {
  it('只包含 < messageId 的轮次', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.input.history).toHaveLength(3)  // 845, 846, 847
  })

  it('history 排除 target message 本身 (id=848)', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.input.history.find((h: any) => h.content === 'agent 这次回复')).toBeUndefined()
  })
})

describe('toYAML - 元数据', () => {
  it('source 含 feedback_id + message_id + user + created_at', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.source.feedback_id).toBe(113)
    expect(parsed.source.message_id).toBe(847)
    expect(parsed.source.user).toBe('eval-test')
    expect(parsed.source.original_comment).toBe('推荐不准')
  })

  it('tags 含 feedback-imported + user-reported + 原 tags', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.tags).toEqual(['feedback-imported', 'user-reported', 'recommend'])
  })

  it('description 含 feedbackId + comment', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.description).toContain('#113')
    expect(parsed.description).toContain('推荐不准')
  })
})

describe('toYAML - 截断', () => {
  it('content 超 10KB 截断', () => {
    const huge = 'a'.repeat(15000)
    const input = {
      ...baseInput,
      conversationMessages: [
        { id: 847, role: 'user' as const, content: huge, createdAt: new Date() },
        { id: 848, role: 'assistant' as const, content: 'agent 这次回复', createdAt: new Date() },
      ],
    }
    const parsed = yaml.load(toYAML(input)) as any
    expect(parsed.input.message).toContain('[已截断]')
    expect(parsed.input.message.length).toBeLessThanOrEqual(15000)
  })
})

describe('toYAML - id slug', () => {
  it('id 格式: feedback-{id}-{user}-{msg}', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.id).toMatch(/^feedback-113-eval-test-/)
  })
})

describe('toYAML - evaluators 默认', () => {
  it('默认 evaluators: schema_check + keyword_coverage', () => {
    const parsed = yaml.load(toYAML(baseInput)) as any
    expect(parsed.evaluators).toEqual(['schema_check', 'keyword_coverage'])
  })
})
```

- [ ] **Step 3: 跑测试验证通过**

```bash
cd trip-server && pnpm test src/services/__tests__/fixtureConverter.test.ts
```
Expected: PASS，10+ 个测试

- [ ] **Step 4: Commit**

```bash
git add trip-server/src/services/fixtureConverter.ts trip-server/src/services/__tests__/fixtureConverter.test.ts trip-server/package.json
git commit -m "feat(fixture): converter core (YAML serializer for feedback)

  - toYAML(input) -> string
  - input.message 选 < messageId 的最后 user turn
  - history 过滤掉 target message 自身
  - slugify 兼容中文/英文/数字
  - 10KB content 截断
  - 10 unit tests in fixtureConverter.test.ts"
```

---

## Task 3: feedbackService.convertToFixture 方法

**Files:**
- Modify: `trip-server/src/services/feedbackService.ts`
- Modify: `trip-server/src/services/__tests__/feedbackService.test.ts`

- [ ] **Step 1: 在 feedbackService.ts 加 import + 方法**

在 `import` 块下加：
```typescript
import { toYAML as convertFeedbackToYAML, ConvertInput as ConverterInput } from './fixtureConverter'
import * as fs from 'fs/promises'
import * as path from 'path'
```

在 class 内最后加新方法（在 `private formatDateKey` 之前）：
```typescript
  /**
   * 把单条负反馈转 fixture YAML 字符串 + 写到 generated/ 目录
   * @returns 写入的文件绝对路径
   */
  async convertToFixture(feedbackId: number): Promise<string> {
    const fb = await prisma.feedback.findUnique({
      where: { id: feedbackId },
      include: {
        user: { select: { username: true, preferences: true } },
      },
    })
    if (!fb) throw new Error(`feedback #${feedbackId} 不存在`)

    const [message, conversation] = await Promise.all([
      prisma.message.findUnique({ where: { id: fb.messageId } }),
      prisma.conversation.findUnique({
        where: { id: fb.conversationId },
        include: {
          messages: { orderBy: { createdAt: 'asc' }, select: { id: true, role: true, content: true, createdAt: true } },
        },
      }),
    ])
    if (!message) throw new Error(`feedback #${feedbackId} 关联的 message #${fb.messageId} 不存在`)
    if (!conversation) throw new Error(`feedback #${feedbackId} 关联的 conversation #${fb.conversationId} 不存在`)

    const converterInput: ConverterInput = {
      feedbackId: fb.id,
      feedbackComment: fb.comment,
      feedbackTags: Array.isArray(fb.tags) ? (fb.tags as string[]) : null,
      feedbackCreatedAt: fb.createdAt,
      messageId: message.id,
      messageContent: message.content,
      userId: fb.userId,
      username: fb.user.username,
      userPreferences: (fb.user.preferences as Record<string, any> | null) ?? null,
      conversationMessages: conversation.messages as any,
    }

    const yamlStr = convertFeedbackToYAML(converterInput)

    // 写文件
    const dir = path.resolve(__dirname, '../../eval/fixtures/generated')
    await fs.mkdir(dir, { recursive: true })
    let filePath = path.join(dir, `${converterInput.feedbackId}-${slugifyFilename(converterInput.username)}.yaml`)
    let counter = 1
    while (true) {
      try {
        await fs.access(filePath)
        filePath = path.join(dir, `${converterInput.feedbackId}-${slugifyFilename(converterInput.username)}-${counter}.yaml`)
        counter++
      } catch {
        break
      }
    }
    await fs.writeFile(filePath, yamlStr, 'utf8')
    log.info({ feedbackId, filePath }, 'fixture 骨架已生成')
    return filePath
  }
```

加一个模块级 helper（在 class 外）：
```typescript
function slugifyFilename(text: string): string {
  return text.replace(/[^\w\u4e00-\u9fa5-]+/g, '-').toLowerCase() || 'user'
}
```

- [ ] **Step 2: 写 service 集成测试（在 feedbackService.test.ts 加 2 个）**

```typescript
  describe('convertToFixture', () => {
    it('写入 YAML 文件到 generated 目录', async () => {
      const path = await feedbackService.convertToFixture(1)
      expect(path).toContain('eval/fixtures/generated/')
      expect(path).toMatch(/\.yaml$/)
    })

    it('feedback 不存在抛错', async () => {
      await expect(feedbackService.convertToFixture(99999)).rejects.toThrow('不存在')
    })
  })
```

- [ ] **Step 3: 跑测试验证通过**

```bash
cd trip-server && pnpm test src/services/__tests__/feedbackService.test.ts
```
Expected: PASS，18 个测试（原 16 + 新 2）

- [ ] **Step 4: typecheck**

```bash
cd trip-server && pnpm typecheck
```
Expected: 无错

- [ ] **Step 5: Commit**

```bash
git add trip-server/src/services/feedbackService.ts trip-server/src/services/__tests__/feedbackService.test.ts
git commit -m "feat(feedback): service.convertToFixture() + 2 unit tests

  - 拉 feedback + user + message + conversation.messages
  - 调 fixtureConverter.toYAML
  - 写 eval/fixtures/generated/{id}-{user}.yaml
  - 冲突时递增后缀 (.yaml / -1.yaml / -2.yaml)
  - feedback/message/conversation 任一不存在 → 抛错"
```

---

## Task 4: API 端点

**Files:**
- Modify: `trip-server/src/controllers/feedback.controller.ts`
- Modify: `trip-server/src/routes/feedback.routes.ts`

- [ ] **Step 1: 在 feedback.controller.ts 加 controller 方法**

```typescript
  /**
   * admin: 批量转 feedback → fixture YAML 文件
   * POST /api/feedback/admin/convert-to-fixture
   * body: { feedbackIds: number[] }
   */
  convertToFixture = async (req: Request, res: Response, next: NextFunction) => {
    try {
      const { feedbackIds } = req.body as { feedbackIds: number[] }
      if (!Array.isArray(feedbackIds) || feedbackIds.length === 0) {
        return res.status(400).json({ code: 1, msg: 'feedbackIds 必填' })
      }
      if (feedbackIds.length > 50) {
        return res.status(400).json({ code: 1, msg: '最多 50 条' })
      }
      if (req.user!.roleId !== 1) {
        return res.status(403).json({ code: 1, msg: '仅管理员可访问' })
      }

      const files: string[] = []
      const skipped: Array<{ id: number; reason: string }> = []
      for (const id of feedbackIds) {
        try {
          const file = await feedbackService.convertToFixture(id)
          files.push(file)
        } catch (e) {
          skipped.push({ id, reason: e instanceof Error ? e.message : String(e) })
        }
      }
      res.json({ code: 0, data: { files, skipped } })
    } catch (e) {
      next(e)
    }
  }
```

- [ ] **Step 2: 在 feedback.routes.ts 加路由**

```typescript
router.post('/admin/convert-to-fixture', authenticate, feedbackController.convertToFixture)
```

- [ ] **Step 3: typecheck**

```bash
cd trip-server && pnpm typecheck
```
Expected: 无错

- [ ] **Step 4: E2E 验证（admin）**

```bash
cd trip-server
# 启服务（后台）
nohup pnpm dev > /tmp/feedback-to-fixture.log 2>&1 &

# 等启动
sleep 8

# 登录
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"eval-test","password":"EvalTest@2026"}' | jq -r .data.token)

# 调 API
curl -s -X POST http://localhost:3000/api/feedback/admin/convert-to-fixture \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"feedbackIds":[1]}' | jq
```
Expected: `{ "code": 0, "data": { "files": ["..."], "skipped": [] } }`

检查文件：
```bash
ls trip-server/eval/fixtures/generated/
cat trip-server/eval/fixtures/generated/*.yaml | head -20
```

- [ ] **Step 5: E2E 验证（roleId=2 → 403）**

```bash
# 改 eval-test roleId 为 2
node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.user.update({ where: { username: 'eval-test' }, data: { roleId: 2 } })
  .then(() => p.\$disconnect());
"

# 重新登录拿新 token
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"eval-test","password":"EvalTest@2026"}' | jq -r .data.token)

# 调 → 403
curl -s -X POST http://localhost:3000/api/feedback/admin/convert-to-fixture \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"feedbackIds":[1]}' | jq
```
Expected: `{ "code": 1, "msg": "仅管理员可访问" }` (HTTP 403)

- [ ] **Step 6: 还原 roleId=1 + 关服务**

```bash
node -e "
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();
p.user.update({ where: { username: 'eval-test' }, data: { roleId: 1 } })
  .then(() => p.\$disconnect());
"
# 杀掉后台服务
pkill -f "nodemon.*trip-server" || true
```

- [ ] **Step 7: Commit**

```bash
git add trip-server/src/controllers/feedback.controller.ts trip-server/src/routes/feedback.routes.ts
git commit -m "feat(api): POST /api/feedback/admin/convert-to-fixture

  - body: { feedbackIds: number[] }
  - admin only (roleId=1)
  - 1-50 ids
  - 逐条转换，失败放入 skipped（不阻断）
  - E2E verified: admin 200, roleId=2 → 403"
```

---

## Task 5: 前端 API + Dashboard 按钮

**Files:**
- Modify: `trip-front/src/api/feedback.ts`
- Modify: `trip-front/src/views/AdminFeedbackDashboard.vue`

- [ ] **Step 1: 在 api/feedback.ts 加 convertToFixture**

```typescript
export interface ConvertToFixtureResponse {
  files: string[]
  skipped: Array<{ id: number; reason: string }>
}

export async function convertFeedbackToFixture(feedbackIds: number[]): Promise<ConvertToFixtureResponse> {
  const res = await request.post<{ code: number; data: ConvertToFixtureResponse }>(
    '/api/feedback/admin/convert-to-fixture',
    { feedbackIds }
  )
  return res.data.data
}
```

- [ ] **Step 2: 在 AdminFeedbackDashboard.vue 加按钮 + modal**

加到 `<script setup>`：
```typescript
import { convertFeedbackToFixture } from '@/api/feedback'
import { showSuccessToast, showFailToast } from 'vant'

const showConvertModal = ref(false)
const convertResult = ref<{ files: string[]; skipped: Array<{ id: number; reason: string }> }>({ files: [], skipped: [] })
const converting = ref(false)
const selectedCaseIds = ref<number[]>([])

async function convertOne(feedbackId: number) {
  converting.value = true
  try {
    const result = await convertFeedbackToFixture([feedbackId])
    convertResult.value = result
    showConvertModal.value = true
    if (result.files.length > 0) showSuccessToast(`已生成 ${result.files.length} 个 fixture`)
  } catch (e: any) {
    showFailToast(e?.message || '转换失败')
  } finally {
    converting.value = false
  }
}

async function convertBatch(days: number = 7) {
  const allIds = highTokenCases.value.map((c: any) => c.feedbackId)
  if (allIds.length === 0) {
    showFailToast('当前没有负反馈案例')
    return
  }
  converting.value = true
  try {
    const result = await convertFeedbackToFixture(allIds)
    convertResult.value = result
    showConvertModal.value = true
    showSuccessToast(`已生成 ${result.files.length} 个 fixture`)
  } catch (e: any) {
    showFailToast(e?.message || '批量转换失败')
  } finally {
    converting.value = false
  }
}
```

在 case 列表行加按钮（在 `{{ c.usage.total }}` 行附近）：
```vue
<van-button size="mini" type="primary" plain :loading="converting" @click="convertOne(c.feedbackId)">
  📋 转 fixture
</van-button>
```

在页面顶部加批量按钮（high-token 区块上方）：
```vue
<van-button block type="primary" plain :loading="converting" @click="convertBatch(7)">
  批量转最近 7 天负反馈
</van-button>
```

加 modal（在 template 末尾）：
```vue
<van-dialog v-model:show="showConvertModal" title="Fixture 骨架已生成" :show-confirm-button="false">
  <div style="padding: 16px">
    <p>已生成 <strong>{{ convertResult.files.length }}</strong> 个文件：</p>
    <ul>
      <li v-for="f in convertResult.files" :key="f" style="font-family: monospace; font-size: 12px; word-break: break-all">
        {{ f }}
      </li>
    </ul>
    <p v-if="convertResult.skipped.length > 0" style="color: orange">
      跳过 {{ convertResult.skipped.length }} 条：
      <ul>
        <li v-for="s in convertResult.skipped" :key="s.id">
          feedback #{{ s.id }}: {{ s.reason }}
        </li>
      </ul>
    </p>
    <p style="color: #999; font-size: 12px">请到 IDE 编辑文件，补 expected 段后 commit。</p>
  </div>
  <template #footer>
    <van-button @click="showConvertModal = false">完成</van-button>
  </template>
</van-dialog>
```

- [ ] **Step 3: typecheck**

```bash
cd trip-front && pnpm typecheck
```
Expected: 无错

- [ ] **Step 4: 手动验证（可选，启前端服务）**

```bash
cd trip-front
nohup pnpm dev > /tmp/trip-front.log 2>&1 &
sleep 8
# 浏览器访问 http://localhost:5173
# 登录 eval-test / EvalTest@2026
# 进入 /admin/feedback
# 点"📋 转 fixture"按钮
# 验证 modal 显示生成的文件
pkill -f "vite.*trip-front" || true
```

- [ ] **Step 5: Commit**

```bash
git add trip-front/src/api/feedback.ts trip-front/src/views/AdminFeedbackDashboard.vue
git commit -m "feat(front): admin dashboard 'convert to fixture' button + modal

  - api/feedback.ts: convertFeedbackToFixture(ids)
  - Dashboard:
    * 每行 case 加 '📋 转 fixture' 按钮
    * 顶部加批量按钮 '批量转最近 7 天负反馈'
    * 转换后弹 modal 显示文件列表 + 跳过原因
    * Toast 提示成功/失败"
```

---

## Task 6: runner 扫 generated/ 目录 + 报告 byTag

**Files:**
- Modify: `trip-server/eval/runner.ts`

- [ ] **Step 1: 找到 fixture 加载代码**

```bash
cd trip-server && grep -n "fixtures/trip-planning" eval/runner.ts
```

- [ ] **Step 2: 改成扫 fixtures 根目录的子目录**

找到原代码（典型）：
```typescript
const FIXTURE_DIR = path.resolve(__dirname, 'fixtures/trip-planning')
```

改成：
```typescript
const FIXTURE_DIR = path.resolve(__dirname, 'fixtures')

async function findFixtureFiles(dir: string): Promise<string[]> {
  const out: string[] = []
  const entries = await fs.readdir(dir, { withFileTypes: true })
  for (const e of entries) {
    const full = path.join(dir, e.name)
    if (e.isDirectory()) {
      out.push(...(await findFixtureFiles(full)))
    } else if (e.name.endsWith('.yaml') && e.name !== '.gitkeep') {
      out.push(full)
    }
  }
  return out
}
```

替换原 `fs.readdir` 加载逻辑。

- [ ] **Step 3: typecheck + 跑 eval 确认旧 fixture 仍加载**

```bash
cd trip-server && pnpm typecheck
cd trip-server && pnpm eval 2>&1 | tail -30
```
Expected: 加载 10+ fixture（数量至少 10，generated 目录是空的）

- [ ] **Step 4: Commit**

```bash
git add trip-server/eval/runner.ts
git commit -m "feat(eval): runner scans fixtures/{**/}*.yaml (trip-planning + generated)

  - 递归扫所有子目录（trip-planning/, generated/）
  - 过滤 .gitkeep
  - 不动 byTag 逻辑（feedback-imported tag 自动出现在 byTag 报告）"
```

---

## Task 7: CLI 脚本

**Files:**
- Create: `trip-server/scripts/feedback-to-fixture.ts`
- Modify: `trip-server/package.json`

- [ ] **Step 1: 写 CLI 脚本**

```typescript
#!/usr/bin/env ts-node
/**
 * feedback-to-fixture CLI
 *
 * 用法：
 *   pnpm feedback:to-fixture --feedback-id=113
 *   pnpm feedback:to-fixture --days=7
 *   pnpm feedback:to-fixture --days=7 --dry-run
 *   pnpm feedback:to-fixture --days=7 --out=custom/dir/
 *
 * 把生产环境的负反馈（rating=-1）转成 eval fixture 骨架 YAML，
 * 输出到 trip-server/eval/fixtures/generated/。
 *
 * 流程：
 *   1) 拉指定时间窗口内所有 rating=-1 的 feedback
 *   2) 逐条调 feedbackService.convertToFixture() 写文件
 *   3) 打印汇总（成功/跳过/警告）
 *
 * 注意：CLI 不鉴权（admin 手动执行，等价 dev 工具）。
 */

import { feedbackService } from '../src/services/feedbackService'
import prisma from '../src/config/database'

interface Args {
  feedbackId?: number
  days?: number
  out?: string
  dryRun: boolean
}

function parseArgs(): Args {
  const argv = process.argv.slice(2)
  const args: Args = { dryRun: false }
  for (const a of argv) {
    if (a.startsWith('--feedback-id=')) args.feedbackId = parseInt(a.split('=')[1], 10)
    else if (a.startsWith('--days=')) args.days = parseInt(a.split('=')[1], 10)
    else if (a.startsWith('--out=')) args.out = a.split('=')[1]
    else if (a === '--dry-run') args.dryRun = true
  }
  return args
}

async function main() {
  const args = parseArgs()
  let feedbackIds: number[] = []

  if (args.feedbackId !== undefined) {
    feedbackIds = [args.feedbackId]
  } else if (args.days !== undefined) {
    const since = new Date(Date.now() - args.days * 24 * 60 * 60 * 1000)
    const downs = await prisma.feedback.findMany({
      where: { createdAt: { gte: since }, rating: -1 },
      select: { id: true },
      orderBy: { createdAt: 'desc' },
      take: 50,
    })
    feedbackIds = downs.map((d) => d.id)
    console.log(`[info] 找到 ${feedbackIds.length} 条 ${args.days} 天内的负反馈`)
  } else {
    console.error('错误：必须传 --feedback-id=N 或 --days=N')
    process.exit(1)
  }

  if (args.dryRun) {
    console.log(`[dry-run] 将处理 ${feedbackIds.length} 条 feedback：${feedbackIds.join(', ')}`)
    console.log(`[dry-run] 不写文件，仅打印。去掉 --dry-run 真正执行。`)
    return
  }

  const success: string[] = []
  const skipped: Array<{ id: number; reason: string }> = []
  for (const id of feedbackIds) {
    try {
      const file = await feedbackService.convertToFixture(id)
      success.push(file)
      console.log(`[ok] feedback #${id} → ${file}`)
    } catch (e) {
      const reason = e instanceof Error ? e.message : String(e)
      skipped.push({ id, reason })
      console.warn(`[skip] feedback #${id}：${reason}`)
    }
  }

  console.log(`\n[summary]`)
  console.log(`  ✓ 成功: ${success.length}`)
  console.log(`  ✗ 跳过: ${skipped.length}`)
  if (skipped.length > 0) {
    for (const s of skipped) console.log(`    - feedback #${s.id}: ${s.reason}`)
  }
  if (success.length > 0) {
    console.log(`\n[next] 请到 IDE 编辑生成的文件，补 expected 段后 git commit。`)
  }
  await prisma.$disconnect()
}

main().catch((e) => {
  console.error('[fatal]', e)
  process.exit(1)
})
```

- [ ] **Step 2: 在 package.json 加 npm script**

```json
"feedback:to-fixture": "ts-node scripts/feedback-to-fixture.ts"
```

- [ ] **Step 3: typecheck + dry-run 验证**

```bash
cd trip-server && pnpm typecheck
cd trip-server && pnpm feedback:to-fixture --days=7 --dry-run
```
Expected: `[dry-run] 将处理 N 条 feedback...`

- [ ] **Step 4: 真实跑一次**

```bash
cd trip-server && pnpm feedback:to-fixture --days=7
ls trip-server/eval/fixtures/generated/
```
Expected: 看到生成的 .yaml 文件

- [ ] **Step 5: Commit**

```bash
git add trip-server/scripts/feedback-to-fixture.ts trip-server/package.json
git commit -m "feat(cli): feedback:to-fixture script

  - pnpm feedback:to-fixture --feedback-id=113 (单条)
  - pnpm feedback:to-fixture --days=7 (批量)
  - --dry-run 不写文件
  - 调 feedbackService.convertToFixture()
  - 打印 ok / skip / summary
  - 不鉴权（admin 手动执行）"
```

---

## Task 8: 文档

**Files:**
- Create: `docs/feedback-to-fixture.md`
- Modify: `docs/feedback-dashboard.md`

- [ ] **Step 1: 写 docs/feedback-to-fixture.md**

```markdown
# Feedback → Fixture 自动化

> 配套 `docs/feedback-dashboard.md`、`docs/online-feedback.md`

## 目标

把生产环境"用户真踩过的坑"自动转成 CI 测试——质量改进闭环最后一公里。

## 流程

```
用户在 ChatBubble 点 👎 + 写评论"推荐不准"
  ↓
admin 在 dashboard 看到该 case
  ↓
点 "📋 转 fixture" 按钮（或批量）
  ↓
生成 eval/fixtures/generated/{id}-{user}.yaml 骨架
  ↓
admin 到 IDE 补 expected 段（10 行 YAML）
  ↓
git commit + CI 自动跑
  ↓
未来若 agent 退化 → CI 红 → 必须修
```

## 3 种使用方式

### 1. Admin Dashboard（推荐给非技术使用）

1. 登录 admin 账号 → Home → 反馈 Dashboard
2. "高 token + 低满意度案例"区，每行点 "📋 转 fixture"
3. 弹 modal 显示文件路径
4. 到 IDE 编辑 `trip-server/eval/fixtures/generated/*.yaml`
5. 补 `expected.must_contain_keywords` 和 `expected.must_not_contain_keywords`
6. `git add` + commit

### 2. CLI

```bash
cd trip-server

# 单条
pnpm feedback:to-fixture --feedback-id=113

# 批量（最近 7 天所有负反馈，最多 50 条）
pnpm feedback:to-fixture --days=7

# 预览不写
pnpm feedback:to-fixture --days=7 --dry-run
```

### 3. API

```bash
TOKEN=$(curl -s -X POST http://localhost:3000/api/user/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"..."}' | jq -r .data.token)

curl -X POST http://localhost:3000/api/feedback/admin/convert-to-fixture \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"feedbackIds": [113, 114]}'
```

## 生成的 YAML 骨架

```yaml
id: feedback-113-eval-test-shanghai-food
description: 来自生产反馈 #113：推荐不准
tags: [feedback-imported, user-reported, recommend]
source:
  feedback_id: 113
  message_id: 847
  user: eval-test
  created_at: 2026-06-24T10:00:00.000Z
  original_comment: 推荐不准
input:
  message: 上海 2 天推荐几个好吃的  # ← 自动取的 user turn
  preferences: { travelStyle: relaxed, interests: [美食] }
  history:
    - { role: user, content: ... }
    - { role: assistant, content: ... }
expected:
  # TODO: 手动补
  must_contain_keywords: []
  must_not_contain_keywords: []
evaluators:
  - schema_check
  - keyword_coverage
```

## Admin 补 expected 模板

```yaml
expected:
  # 案例：用户说"推荐不准"
  must_contain_keywords: [推荐, 餐厅, 美食]  # 该有的关键词
  must_not_contain_keywords: [酒吧, 夜店]  # 不该有的
  
  # 案例：用户说"没解决宠物问题"
  must_contain_keywords: [宠物, 友好, 允许携带]
  
  # 案例：用户说"行程太紧凑"
  max_activities_per_day: 4
  
  # 工具调用：期望 RAG 召回
  tool_calls:
    - { name: retrieve_knowledge, min_calls: 1 }
```

## 报告

跑 `pnpm eval --real` 后，报告里：
- `byTag.feedback-imported`：所有反馈来源 fixture 通过率
- `byTag.user-reported`：同上
- 单个 case 显示 `source: feedback #113` 元数据（在 fixture description 里）

## 限制

- **半自动**：`expected` 段必须 admin 手动补（10 行 YAML，2-3 分钟）
- **批量上限 50**：避免 admin 压力
- **不自动 commit**：避免 review 缺失
- **历史截断 10KB**：超大 content 截断（fixture 文件应 < 100KB）
- **不转好评**（rating=1）：CLI/API 都跳过

## 验证

```bash
# 生成的 fixture 能跑
pnpm eval --real
# 看到 "feedback-113-eval-test-shanghai-food" 通过/失败

# 单元测试
pnpm test
# fixtureConverter 10 个 + feedbackService 2 个 = 12 个
```
```

- [ ] **Step 2: 在 docs/feedback-dashboard.md 末尾加链接**

加到 "相关文件" 表格下：
```markdown
## 进阶用法

- **反馈 → Fixture 自动化**：见 `docs/feedback-to-fixture.md`（点击 dashboard 案例行 "📋 转 fixture" 按钮即可生成）
```

- [ ] **Step 3: Commit**

```bash
git add docs/feedback-to-fixture.md docs/feedback-dashboard.md
git commit -m "docs: feedback-to-fixture usage guide + dashboard link

  - docs/feedback-to-fixture.md (NEW, ~100 lines):
    * 3 使用方式: Dashboard / CLI / API
    * 生成的 YAML 骨架示例
    * admin 补 expected 模板
    * 报告 + 限制 + 验证
  - docs/feedback-dashboard.md: 末尾加 '反馈 → Fixture 自动化' 链接"
```

---

## Task 9: 实战：生成 1 个 fixture 补 expected 跑通

**Files:**
- Create: `trip-server/eval/fixtures/generated/{id}.yaml`（admin 手动补 expected 后）

- [ ] **Step 1: 跑 CLI 真实生成**

```bash
cd trip-server && pnpm feedback:to-fixture --days=7
ls eval/fixtures/generated/
```

- [ ] **Step 2: 取最新生成的文件 + 手动补 expected**

```bash
ls -t eval/fixtures/generated/*.yaml | head -1
# 在 IDE 打开
# 补 expected.must_contain_keywords / must_not_contain_keywords
# （根据原 feedback.comment 判断）
```

- [ ] **Step 3: 跑 eval 验证 fixture 加载**

```bash
cd trip-server && pnpm eval 2>&1 | tail -20
```
Expected: 报告里看到新 fixture 通过/失败（如果 expected 必含词太严格可能失败，调一下）

- [ ] **Step 4: 跑真实 eval（可选，需 DEEPSEEK_API_KEY）**

```bash
cd trip-server && EVAL_REAL=1 pnpm eval:real 2>&1 | tail -20
```

- [ ] **Step 5: Commit 实战 fixture**

```bash
git add trip-server/eval/fixtures/generated/*.yaml
git commit -m "test(fixture): import 1 feedback case as regression fixture

  - feedback #N: 原 comment '...'
  - 补 expected: must_contain_keywords=[...], must_not_contain_keywords=[...]
  - 防同类问题回归"
```

- [ ] **Step 6: 更新 tasks/todo.md + 在线反馈文档 "后续进度"**

```bash
# 编辑 tasks/todo.md 第 96 行
# 旧: ⏳ **反馈 → fixture**
# 新: ✅ **反馈 → fixture**：见 `docs/feedback-to-fixture.md`

# 编辑 docs/online-feedback.md 后续进度
# 旧: ⏳ 反馈进入 fixture
# 新: ✅ 反馈进入 fixture（Task 3 完成，2026-06-25）
```

- [ ] **Step 7: 最终 commit**

```bash
git add tasks/todo.md docs/online-feedback.md
git commit -m "docs(todo): mark feedback-to-fixture as completed (Task 3)

  - tasks/todo.md: §1 反馈 → fixture ✅
  - docs/online-feedback.md: 后续进度更新"
```

---

## 验证清单

跑完所有 Task 后，最终检查：

- [ ] `cd trip-server && pnpm test` 通过（111 + 12 = 123 测试）
- [ ] `cd trip-server && pnpm typecheck` 通过
- [ ] `cd trip-front && pnpm typecheck` 通过
- [ ] `pnpm feedback:to-fixture --days=7 --dry-run` 跑通
- [ ] `pnpm feedback:to-fixture --days=7` 至少生成 1 个文件
- [ ] 生成的 YAML 加载到 eval 跑（`pnpm eval` 不报错）
- [ ] admin 调 API 200，roleId=2 → 403
- [ ] `docs/feedback-to-fixture.md` 完整
- [ ] 所有 commit 都 pushed

## 总 commit 清单

1. `chore: add js-yaml + created eval/fixtures/generated/`
2. `feat(fixture): converter core`
3. `feat(feedback): service.convertToFixture() + tests`
4. `feat(api): POST /api/feedback/admin/convert-to-fixture`
5. `feat(front): dashboard 'convert to fixture' button + modal`
6. `feat(eval): runner scans fixtures/{**/}*.yaml`
7. `feat(cli): feedback:to-fixture script`
8. `docs: feedback-to-fixture usage guide`
9. `test(fixture): import 1 feedback case as regression fixture`
10. `docs(todo): mark feedback-to-fixture as completed`
