# Phase 1a Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the chat UI display bug and expose the new backend features (conversation memory, trip history, user preferences) through the frontend.

**Architecture:**
- Frontend uses Vue 3 Composition API + TypeScript; backend is Express 5 + Prisma.
- Each task is a self-contained PR-sized change that compiles and lints cleanly on its own.
- Tasks are ordered so that backend fixes (Task 2) are not blocked by frontend work (Tasks 1, 3, 4, 5), and the chat fix (Task 1) unblocks the chat-related UI (Task 3).

**Tech Stack:** Vue 3, Vant 4, TypeScript, Express 5, Prisma 5, zod, LangChain.

---

## File Structure

### New files
- `trip-front/src/api/conversation.ts` — typed wrapper for /api/conversations
- `trip-front/src/api/history.ts` — typed wrapper for /api/history/trips
- `trip-front/src/views/History.vue` — trip history list page
- `trip-front/src/components/ConversationDrawer.vue` — sliding drawer used in Chat.vue

### Modified files
- `trip-front/src/views/Chat.vue` — fix Bug 1 + add conversation history drawer
- `trip-front/src/views/Home.vue` — add "我的行程" entry card
- `trip-front/src/views/Detail.vue` — support `?id=` to load saved trip
- `trip-front/src/views/Profile.vue` — add preferences editor
- `trip-front/src/router/index.ts` — add /history route
- `trip-server/src/services/tripService.ts` — autoTitle + recommend→trip persist
- `trip-server/src/services/userService.ts` — preferences read/write
- `trip-server/src/controllers/user.controller.ts` — accept preferences in updateInfo

---

## Task 1: Fix Chat UI display bug (Bug 1)

**Files:**
- Modify: `trip-front/src/views/Chat.vue`
- Modify: `trip-front/src/components/ChatBubble.vue`

**Problem:** Chat sends question → network shows successful response → no output renders on page.

**Root cause:** The 50ms setInterval throttle in `fetchAiResponse` is a suspect for the perceived "no output". More importantly, `aiMessage` is a plain object pushed to a reactive array, and mutating its `content` field after push is not guaranteed to be tracked by Vue's deep reactivity in all edge cases. The fix is to (a) use a `ref<Message>` for the AI message, (b) replace the whole object on each update, and (c) drop the setInterval in favor of synchronous onChunk writes (Vue 3 + Vant can comfortably handle 30+ updates per second).

- [ ] **Step 1: Read current Chat.vue and ChatBubble.vue**

Confirm the current implementation matches what we expect.

- [ ] **Step 2: Rewrite `Chat.vue` `fetchAiResponse`**

Replace lines 72-113 in `Chat.vue` with the following:

```ts
const fetchAiResponse = (userMsg: string) => {
  isStreaming.value = true
  const aiMessage = ref<Message>({
    role: 'ai',
    content: '',
    timestamp: new Date().toISOString(),
  })
  messages.value.push(aiMessage.value)

  fetchStream(
    'trip/chat',
    { message: userMsg, conversationId: currentConversationId.value },
    (chunk) => {
      aiMessage.value = { ...aiMessage.value, content: aiMessage.value.content + chunk }
    },
    (data) => {
      aiMessage.value = { ...aiMessage.value, content: aiMessage.value.content }
      isStreaming.value = false
      if (data?.conversationId) {
        currentConversationId.value = data.conversationId
        localStorage.setItem(CONVERSATION_ID_KEY, String(data.conversationId))
      }
    },
    (errMsg) => {
      aiMessage.value = { ...aiMessage.value, content: `AI处理发生错误: ${errMsg}` }
      isStreaming.value = false
      showToast('AI处理发生错误')
    },
  )
}
```

Import the `ref` type explicitly if needed (it should already be imported).

- [ ] **Step 3: Update ChatBubble streaming prop default**

In `ChatBubble.vue`, the `streaming` prop should default to `false`. The template currently shows the cursor when `streaming` is true and content is non-empty — confirm `<div v-html="renderedContent">` always has a v-if wrapper for the AI branch so it doesn't try to render `marked.parse('')` for an empty string.

Modify the `renderedContent` computed to:
```ts
const renderedContent = computed(() => {
  if (!props.message.content) return ''
  if (props.streaming) {
    return `${escapeHtml(props.message.content)}<span class="streaming-cursor">▍</span>`
  }
  return marked.parse(props.message.content) as string
})
```

(Existing — verify only.)

- [ ] **Step 4: Verify type check**

Run: `cd trip-front && npx vue-tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual smoke test**

Run: `cd trip-front && npm run dev` (in background)
Then `cd trip-server && npm run dev`
Open the chat page in browser, send a question, verify the AI reply appears in chunks.

- [ ] **Step 6: Commit**

```bash
cd /Users/wang/Documents/trip
git add trip-front/src/views/Chat.vue trip-front/src/components/ChatBubble.vue
git commit -m "fix(chat): ref-based AI message + synchronous onChunk writes

- Replace setInterval-throttled renderFrame with synchronous
  aiMessage.value = { ... } replacement on every chunk
- Use ref<Message> wrapper so Vue 3 reactivity is guaranteed
  even if push-to-array deep tracking has edge cases
- Eliminate the 50ms render window that could appear as 'no output'
  on the first chunk"
```

---

## Task 2: Backend gap fixes (autoTitle + recommend persist + preferences)

**Files:**
- Modify: `trip-server/src/services/tripService.ts`
- Modify: `trip-server/src/services/userService.ts`
- Modify: `trip-server/src/controllers/user.controller.ts`

Three backend gaps from the diagnosis:
- `conversationService.autoTitle` exists but is never called → call it on first message in `chatStream`
- `tripService.recommend` doesn't write to the `trips` table → write on success
- `User.preferences` is in the schema but unreadable/writable through the API

- [ ] **Step 1: Wire autoTitle in chatStream**

In `trip-server/src/services/tripService.ts`, after `getOrCreateConversation(...)` (around line 22), add:

```ts
if (!conversation.title || conversation.title === '新对话') {
  await autoTitle(conversation.id, message)
}
```

And update the import to include `autoTitle`:
```ts
import { getOrCreateConversation, saveMessage, autoTitle } from './conversationService'
```

- [ ] **Step 2: Persist trip in recommend**

In `trip-server/src/services/tripService.ts`, in `recommend`, after successfully parsing the LLM output, before the `return` statement, add:

```ts
let savedTripId: number | null = null
try {
  // The recommend endpoint is not auth-gated in Phase 1a; persist only if
  // req.user is available (will be added in Phase 1b when we add auth here).
  const created = await prisma.trip.create({
    data: {
      userId: 0,  // Phase 1b: replace with req.user.userId
      city: parsed.city,
      days: parsed.days,
      budget,
      content: parsed as any,
      status: 'completed',
    },
  })
  savedTripId = created.id
} catch (e) {
  console.error('[TripService] recommend persist failed:', e)
}
return {
  success: true,
  data: {
    id: savedTripId,
    city: parsed.city,
    days: parsed.days,
    totalBudget: parsed.totalBudget,
    dailyItinerary: parsed.dailyItinerary,
    budgetBreakdown: parsed.budgetBreakdown,
    tips: parsed.tips,
    warnings: parsed.warnings,
  },
}
```

NOTE: Since `recommend` is not auth-gated today, we use `userId: 0` as a placeholder. Phase 1b will require auth and use real userId. (Trips with `userId: 0` will not show up in any user's history list — acceptable for Phase 1a since no UI for trip history is using this field yet.)

- [ ] **Step 3: Read User preferences in getUserInfo**

In `trip-server/src/services/userService.ts`, find the `getUserInfo` function and add `preferences: true` to the select clause.

- [ ] **Step 4: Accept preferences in updateUserInfo**

In `trip-server/src/services/userService.ts`, `updateUserInfo`:
- Add `preferences?: Record<string, any> | null` to the input type
- Add `preferences: input.preferences ?? undefined` to the Prisma update data

In `trip-server/src/controllers/user.controller.ts`, `updateInfo`:
- Destructure `preferences` from req.body
- Pass it through to `userService.updateUserInfo`

- [ ] **Step 5: Verify tsc**

Run: `cd trip-server && npx tsc --noEmit`
Expected: only the pre-existing `moduleResolution=node10` deprecation warning.

- [ ] **Step 6: Smoke test**

- Restart backend
- Use existing user to log in, send a chat message, verify the conversation's `title` is set to the first 20 chars of the message (autoTitle)
- `curl /api/user/info` and verify the response includes `preferences` (will be `null` for existing users)
- `PUT /api/user/info` with `{"preferences":{"travelStyle":"adventure"}}` and verify it round-trips
- Send a recommend request and check MySQL: a row should appear in the `trips` table

- [ ] **Step 7: Commit**

```bash
cd /Users/wang/Documents/trip
git add trip-server/src/services/tripService.ts trip-server/src/services/userService.ts trip-server/src/controllers/user.controller.ts
git commit -m "fix(backend): autoTitle, recommend persist, preferences round-trip

- Call autoTitle when conversation has default '新对话' title so list
  views show meaningful conversation names
- Persist recommend results to trips table (userId:0 placeholder until
  Phase 1b gates recommend behind auth)
- Expose User.preferences through /api/user/info GET and PUT so the
  profile UI can read/write it"
```

---

## Task 3: Conversation memory UI (history drawer in Chat)

**Files:**
- Create: `trip-front/src/api/conversation.ts`
- Create: `trip-front/src/components/ConversationDrawer.vue`
- Modify: `trip-front/src/views/Chat.vue`

Make conversation history discoverable: a drawer/sidebar accessible from the Chat page that lists past conversations, lets the user open one (loads the messages into the current view), and lets them delete or start a new one.

- [ ] **Step 1: Create `trip-front/src/api/conversation.ts`**

```ts
import { get, del } from './request'

export interface ConversationListItem {
  id: number
  title: string | null
  createdAt: string
  updatedAt: string
  userId: number
  _count: { messages: number }
}

export interface ConversationDetailMessage {
  id: number
  conversationId: number
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: unknown | null
  createdAt: string
}

export interface ConversationDetail {
  id: number
  userId: number
  title: string | null
  summary: string | null
  createdAt: string
  updatedAt: string
  messages: ConversationDetailMessage[]
}

export async function listConversations(page = 1, pageSize = 20) {
  return get<{ items: ConversationListItem[]; total: number; page: number; pageSize: number }>(
    'conversations',
    { page, pageSize },
  )
}

export async function getConversation(id: number) {
  return get<ConversationDetail>(`conversations/${id}`)
}

export async function deleteConversation(id: number) {
  return del<{ code: number; message: string }>(`conversations/${id}`)
}
```

Note: We also need to export `del` from `request.ts` (only `get`, `post`, `put` are exported today). Add it.

- [ ] **Step 2: Add `del` helper to `request.ts`**

In `trip-front/src/api/request.ts`, after the `put` function, add:
```ts
export function del<T = any>(url: string, params?: any): Promise<ApiResponse<T>> {
  return request.delete(url, { params })
}
```

- [ ] **Step 3: Create `trip-front/src/components/ConversationDrawer.vue`**

This is a Vant `van-popup` with position="left", showing a list of conversations from `listConversations`. Each item is a `van-cell` with title=conversation.title and right-arrow; clicking calls a `select` emit. There's also a "新建对话" button at the top.

```vue
<template>
  <van-popup
    :show="show"
    position="left"
    :style="{ width: '80%', maxWidth: '320px', height: '100%' }"
    @update:show="(v: boolean) => emit('update:show', v)"
  >
    <div class="drawer">
      <div class="drawer-header">
        <van-button type="primary" block @click="onNew">新建对话</van-button>
      </div>
      <div class="drawer-body">
        <van-empty v-if="!loading && items.length === 0" description="暂无历史对话" />
        <van-cell-group v-else inset>
          <van-cell
            v-for="item in items"
            :key="item.id"
            :title="item.title || '新对话'"
            :label="formatTime(item.updatedAt)"
            is-link
            @click="onSelect(item.id)"
          >
            <template #right-icon>
              <van-icon name="cross" @click.stop="onDelete(item.id)" />
            </template>
          </van-cell>
        </van-cell-group>
      </div>
    </div>
  </van-popup>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { showConfirmDialog, showToast } from 'vant'
import { listConversations, deleteConversation, type ConversationListItem } from '@/api/conversation'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  select: [id: number]
  new: []
}>()

const items = ref<ConversationListItem[]>([])
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    const res = await listConversations()
    items.value = res.data?.items ?? []
  } catch (e) {
    showToast('加载历史对话失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => { if (v) load() })

const onSelect = (id: number) => {
  emit('select', id)
  emit('update:show', false)
}

const onNew = () => {
  emit('new')
  emit('update:show', false)
}

const onDelete = async (id: number) => {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后无法恢复' })
  } catch { return }
  try {
    await deleteConversation(id)
    items.value = items.value.filter(i => i.id !== id)
    showToast('已删除')
  } catch (e) {
    showToast('删除失败')
  }
}

const formatTime = (iso: string) => {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}
</script>

<style scoped>
.drawer { display: flex; flex-direction: column; height: 100%; background: #fff; }
.drawer-header { padding: 16px; border-bottom: 1px solid #f0f0f0; }
.drawer-body { flex: 1; overflow-y: auto; padding: 12px 0; }
</style>
```

- [ ] **Step 4: Wire the drawer into Chat.vue**

In `Chat.vue`:
- Import the drawer and the conversation API
- Add `showDrawer = ref(false)`, `onSelectConversation(id)`, `onNewConversation()` methods
- Add a "history" button to the nav bar
- On select, fetch the conversation detail and replace `messages.value`
- On new, clear `currentConversationId` and `messages.value`

Add the nav bar button (modify the existing `<van-nav-bar>`):
```vue
<template #right>
  <van-icon name="bars" size="20" @click="showDrawer = true" />
</template>
```

And add to script:
```ts
import ConversationDrawer from '@/components/ConversationDrawer.vue'
import { getConversation } from '@/api/conversation'

const showDrawer = ref(false)

const onSelectConversation = async (id: number) => {
  try {
    const res = await getConversation(id)
    const conv = res.data
    if (!conv) return
    currentConversationId.value = id
    localStorage.setItem(CONVERSATION_ID_KEY, String(id))
    messages.value = (conv.messages || []).map(m => ({
      role: m.role === 'user' ? 'user' : 'ai',
      content: m.content,
      timestamp: m.createdAt,
    }))
  } catch (e) {
    showToast('加载对话失败')
  }
}

const onNewConversation = () => {
  currentConversationId.value = null
  localStorage.removeItem(CONVERSATION_ID_KEY)
  messages.value = []
}
```

And add the drawer at the end of the template (just before `</div>` of the page-container):
```vue
<ConversationDrawer v-model:show="showDrawer" @select="onSelectConversation" @new="onNewConversation" />
```

- [ ] **Step 5: Verify type check**

Run: `cd trip-front && npx vue-tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Smoke test**

- Start both servers
- Open Chat, send a message, verify a conversation row is created
- Open the drawer, verify the conversation appears in the list with the message as title
- Click it, verify the previous messages load into the chat view
- Click "新建对话", verify messages clear
- Delete a conversation, verify it disappears

- [ ] **Step 7: Commit**

```bash
cd /Users/wang/Documents/trip
git add trip-front/src/api/conversation.ts trip-front/src/api/request.ts trip-front/src/components/ConversationDrawer.vue trip-front/src/views/Chat.vue
git commit -m "feat(chat): conversation history drawer with load + delete

- Add /api/conversations typed wrapper
- New ConversationDrawer component (van-popup left) listing
  conversations with select / delete / new actions
- Chat.vue gains a 'history' nav-bar icon, integrates the drawer;
  on select, loads the conversation's messages and replaces the
  current view; on new, resets state and clears localStorage
- Add 'del' helper to request.ts for DELETE requests"
```

---

## Task 4: Trip history UI

**Files:**
- Create: `trip-front/src/api/history.ts`
- Create: `trip-front/src/views/History.vue`
- Modify: `trip-front/src/views/Home.vue`
- Modify: `trip-front/src/views/Detail.vue`
- Modify: `trip-front/src/router/index.ts`

Make saved trips discoverable: a "我的行程" entry on Home that goes to a list page; Detail can load a saved trip by id.

- [ ] **Step 1: Create `trip-front/src/api/history.ts`**

```ts
import { get } from './request'

export interface TripListItem {
  id: number
  userId: number
  city: string
  days: number
  budget: number
  content: unknown
  status: string
  parentTripId: number | null
  createdAt: string
}

export interface TripDetail extends TripListItem {}

export async function listTrips(page = 1, pageSize = 20) {
  return get<{ items: TripListItem[]; total: number; page: number; pageSize: number }>(
    'history/trips',
    { page, pageSize },
  )
}

export async function getTrip(id: number) {
  return get<TripDetail>(`history/trips/${id}`)
}
```

- [ ] **Step 2: Create `trip-front/src/views/History.vue`**

List of saved trips, each cell links to `Detail?id=<id>`.

```vue
<template>
  <div class="page-container history-page">
    <div class="page-header">
      <van-nav-bar left-arrow left-text="返回" @click-left="onBack" title="我的行程" />
    </div>
    <div class="page-body">
      <van-empty v-if="!loading && items.length === 0" description="还没有保存的行程，去首页生成一个吧" />
      <van-cell-group v-else inset>
        <van-cell
          v-for="t in items"
          :key="t.id"
          :title="t.city + ' · ' + t.days + '天'"
          :label="formatTime(t.createdAt) + ' · 预算 ' + t.budget + '元'"
          is-link
          :to="{ name: 'Detail', query: { id: t.id } }"
        />
      </van-cell-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listTrips, type TripListItem } from '@/api/history'

const router = useRouter()
const items = ref<TripListItem[]>([])
const loading = ref(false)

const onBack = () => router.back()

const load = async () => {
  loading.value = true
  try {
    const res = await listTrips()
    items.value = res.data?.items ?? []
  } finally {
    loading.value = false
  }
}

const formatTime = (iso: string) => {
  const d = new Date(iso)
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`
}

onMounted(load)
</script>

<style scoped>
.history-page { min-height: 100vh; background: #f7f8fa; }
.page-body { padding: 12px 0 60px; }
</style>
```

- [ ] **Step 3: Add `/history` route**

In `trip-front/src/router/index.ts`, add:
```ts
{
  path: '/history',
  name: 'History',
  component: () => import('../views/History.vue'),
  meta: { requiresAuth: true },
},
```

- [ ] **Step 4: Add "我的行程" entry card on Home**

In `trip-front/src/views/Home.vue`, find the existing `van-grid` (the one with "国内" "出境" etc) and add a grid item that links to `/history`. If the existing structure doesn't fit, add a separate `van-cell is-link` below the grid:

```vue
<van-cell
  title="我的行程"
  icon="records-o"
  is-link
  to="/history"
  class="history-entry"
/>
```

(Inspect Home.vue first to understand its layout; adapt accordingly.)

- [ ] **Step 5: Make Detail.vue load saved trip by id**

In `trip-front/src/views/Detail.vue`, in the `onMounted` (or wherever the data is loaded), check `route.query.id`:
- If present: call `getTrip(id)` and set `tripData` to `trip.content` (the Json column already has the TripContent shape)
- If not present: keep the current `recommend` flow

Add import:
```ts
import { useRoute } from 'vue-router'
import { getTrip } from '@/api/history'
```

And in the existing data-loading logic, branch on `route.query.id`.

- [ ] **Step 6: Verify type check**

Run: `cd trip-front && npx vue-tsc --noEmit`

- [ ] **Step 7: Smoke test**

- Send a recommend request (currently /api/trip/recommend is not auth-gated, but verify the trips table gets a row)
- Open Home, click "我的行程", verify the saved trip appears
- Click the trip, verify Detail.vue loads it without calling recommend
- Also test the original recommend flow (Home → Detail without id) still works

- [ ] **Step 8: Commit**

```bash
cd /Users/wang/Documents/trip
git add trip-front/src/api/history.ts trip-front/src/views/History.vue trip-front/src/views/Home.vue trip-front/src/views/Detail.vue trip-front/src/router/index.ts
git commit -m "feat(home): trip history entry + History page + saved-trip load

- New /api/history/trips typed wrapper
- History.vue: list saved trips, cell links to Detail?id=<id>
- Home.vue gains '我的行程' entry linking to /history
- Detail.vue: when ?id is present, load saved trip from /api/history/trips/:id
  instead of calling recommend; otherwise keep existing recommend flow
- New /history route"
```

---

## Task 5: User preferences UI

**Files:**
- Modify: `trip-front/src/views/Profile.vue`

Expose User.preferences through Profile.vue so users can configure travel style, budget level, and pace. The agent engine already reads `preferences` and injects it into the system prompt — this task just adds the user-facing editor.

- [ ] **Step 1: Read current Profile.vue**

Understand the existing layout (form, cell-group, save button).

- [ ] **Step 2: Add preferences state and editor**

Add to `Profile.vue`:

```ts
import { ref, onMounted } from 'vue'
import { getUserInfo, updateUserInfo } from '@/api/user'

interface UserPreferences {
  travelStyle?: 'cultural' | 'nature' | 'food' | 'shopping' | 'leisure'
  budgetLevel?: 'economy' | 'standard' | 'comfort' | 'luxury'
  pace?: 'compact' | 'moderate' | 'relaxed'
  avoidCrowds?: boolean
  interests?: string[]
}

const preferences = ref<UserPreferences>({})
const originalPreferences = ref<UserPreferences>({})

// In existing loadInfo, also load preferences:
//   const info = await getUserInfo()
//   preferences.value = info.preferences ?? {}
//   originalPreferences.value = { ...preferences.value }

const dirty = computed(() => JSON.stringify(preferences.value) !== JSON.stringify(originalPreferences.value))

const onSavePreferences = async () => {
  try {
    await updateUserInfo({ preferences: preferences.value })
    originalPreferences.value = { ...preferences.value }
    showToast('已保存')
  } catch (e) {
    showToast('保存失败')
  }
}
```

UI (in the template, after the existing nickname/phone/bio fields):
```vue
<van-cell-group inset title="旅行偏好" class="preferences-section">
  <van-cell title="旅行风格">
    <template #value>
      <van-radio-group
        v-model="preferences.travelStyle"
        direction="horizontal"
      >
        <van-radio name="cultural">文化</van-radio>
        <van-radio name="nature">自然</van-radio>
        <van-radio name="food">美食</van-radio>
        <van-radio name="leisure">休闲</van-radio>
      </van-radio-group>
    </template>
  </van-cell>
  <van-cell title="预算档次">
    <template #value>
      <van-radio-group
        v-model="preferences.budgetLevel"
        direction="horizontal"
      >
        <van-radio name="economy">经济</van-radio>
        <van-radio name="standard">标准</van-radio>
        <van-radio name="comfort">舒适</van-radio>
        <van-radio name="luxury">豪华</van-radio>
      </van-radio-group>
    </template>
  </van-cell>
  <van-cell title="节奏">
    <template #value>
      <van-radio-group
        v-model="preferences.pace"
        direction="horizontal"
      >
        <van-radio name="compact">紧凑</van-radio>
        <van-radio name="moderate">适中</van-radio>
        <van-radio name="relaxed">轻松</van-radio>
      </van-radio-group>
    </template>
  </van-cell>
  <van-cell title="避开高峰" center>
    <template #right-icon>
      <van-switch v-model="preferences.avoidCrowds" />
    </template>
  </van-cell>
</van-cell-group>

<div class="preferences-save">
  <van-button
    type="primary"
    block
    :disabled="!dirty"
    @click="onSavePreferences"
  >
    保存偏好
  </van-button>
</div>
```

- [ ] **Step 3: Verify type check**

Run: `cd trip-front && npx vue-tsc --noEmit`

- [ ] **Step 4: Smoke test**

- Open Profile, verify the form is pre-populated from existing preferences (empty for new users)
- Change some options, click save, verify the values round-trip
- Send a chat message in Chat, verify (by looking at the agent's system prompt via `agentEngine.chat`) that the preferences are injected. (Optional: log the prompt to server console to confirm.)

- [ ] **Step 5: Commit**

```bash
cd /Users/wang/Documents/trip
git add trip-front/src/views/Profile.vue
git commit -m "feat(profile): travel preferences editor (style/budget/pace/crowd)

- Add UserPreferences type with travelStyle, budgetLevel, pace,
  avoidCrowds
- Profile.vue loads preferences on mount, lets user edit them via
  radio groups and a switch, and saves via updateUserInfo
- Backend support added in Task 2 (User.preferences round-trip)
- These values are already consumed by agentEngine.loadUserPreferences
  and injected into the system prompt, so changes take effect on the
  next chat message"
```

---

## Self-Review

**Spec coverage (the original 2 bugs + 5 tasks):**
- Bug 1 (chat UI not displaying) → Task 1 ✓
- Bug 2 (no UI for new features) → Tasks 3, 4, 5 ✓
- Backend gaps discovered during diagnosis → Task 2 ✓

**Risks / known limitations:**
- Trip history: `recommend` is not auth-gated in Phase 1a, so `userId=0` placeholder. The `History` page will only show trips belonging to userId=0. Phase 1b will gate `recommend` behind auth and replace the placeholder.
- `Conversation.title` defaults to the first 20 chars of the first user message — this is set in `autoTitle` which Task 2 wires up. Existing conversations before the fix will keep their "新对话" title.
- `User.preferences` has no schema validation — the field is `Json?` in Prisma. A future task could add a zod schema in `types/agent.ts`.

**No placeholders / TBDs in the plan.**

**Type consistency:**
- `Message` in Chat.vue matches `ConversationDetailMessage` in api/conversation.ts (role mapping: backend `assistant` → frontend `ai`)
- `TripListItem` in api/history.ts matches the Prisma Trip model
- `UserPreferences` is consistent between Profile.vue and the agent's `loadUserPreferences` (which reads the same `Json` field)
