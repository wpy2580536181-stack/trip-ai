import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// Node 实验性 localStorage 全局遮蔽 happy-dom 实现，stub 一个内存版
const storageMap = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => storageMap.get(k) ?? null,
  setItem: (k: string, v: string) => storageMap.set(k, String(v)),
  removeItem: (k: string) => storageMap.delete(k),
  clear: () => storageMap.clear(),
})

// naive-ui useMessage/useDialog 需要 provider，只 mock 这两个导出
vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return {
    ...actual,
    useMessage: () => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }),
    useDialog: () => ({ warning: vi.fn() }),
  }
})

// 路由 mock（query 可按测试用例调整）
const mockQuery: Record<string, string> = {}
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: mockQuery }),
  useRouter: () => ({ push: mockPush }),
}))

vi.mock('@/api/conversation', () => ({
  listConversations: vi.fn().mockResolvedValue({ data: { items: [] } }),
  getConversation: vi.fn().mockResolvedValue({ data: null }),
  deleteConversation: vi.fn(),
}))

type StreamCallbacks = {
  body: any
  onChunk: (chunk: string) => void
  onComplete: (data?: any) => void
  onTripEvent?: (type: string, data: any) => void
}
let captured: StreamCallbacks | null = null

vi.mock('@/api/request', () => ({
  fetchStream: vi.fn(
    (
      _url: string,
      body: any,
      onChunk: any,
      onComplete: any,
      _onError: any,
      _onToolEvent: any,
      _onHeartbeat: any,
      _onResume: any,
      options: any,
    ) => {
      captured = { body, onChunk, onComplete, onTripEvent: options?.onTripEvent }
      return Promise.resolve(new AbortController())
    },
  ),
}))

import Chat from '../Chat.vue'

async function mountAndSend(): Promise<{ wrapper: any; cb: StreamCallbacks }> {
  const wrapper = mount(Chat)
  await flushPromises()
  // naive-ui 组件在测试环境未解析（auto-import），直接驱动 setup 状态发送
  wrapper.vm.inputMessage = '帮我改一下行程'
  await nextTick()
  wrapper.vm.sendMessage()
  await flushPromises()
  expect(captured).not.toBeNull()
  return { wrapper, cb: captured! }
}

describe('Chat.vue — 关联行程（Fix 3）', () => {
  beforeEach(() => {
    captured = null
    vi.clearAllMocks()
    storageMap.clear()
    for (const k of Object.keys(mockQuery)) delete mockQuery[k]
  })

  it('route.query.tripId 存在 → 请求体携带 tripId，头部显示徽章', async () => {
    mockQuery.tripId = '7'
    const { wrapper, cb } = await mountAndSend()

    expect(cb.body.tripId).toBe(7)
    expect(wrapper.text()).toContain('关联行程 #7')
  })

  it('无 tripId → 请求体 tripId 为 null，无徽章', async () => {
    const { wrapper, cb } = await mountAndSend()

    expect(cb.body.tripId).toBeNull()
    expect(wrapper.text()).not.toContain('关联行程')
  })

  it('trip_modified 事件 → 关联切到新版本，气泡含摘要与详情链接', async () => {
    mockQuery.tripId = '7'
    const { wrapper, cb } = await mountAndSend()

    cb.onTripEvent!('trip_modified', { newTripId: 99, summary: '已生成修改版行程' })
    cb.onComplete({ conversationId: 5 })
    await flushPromises()

    expect(wrapper.text()).toContain('关联行程 #99')
    expect(wrapper.html()).toContain('/detail?id=99')
    expect(wrapper.text()).toContain('已生成修改版行程')
  })

  it('取消关联 → 后续请求不带 tripId', async () => {
    mockQuery.tripId = '7'
    const { wrapper } = await mountAndSend()
    captured!.onComplete({ conversationId: 5 })
    await flushPromises()

    // 取消关联
    wrapper.vm.clearTripLink()
    await nextTick()
    expect(wrapper.text()).not.toContain('关联行程')

    // 再发一条消息
    captured = null
    wrapper.vm.inputMessage = '再问一个问题'
    await nextTick()
    wrapper.vm.sendMessage()
    await flushPromises()

    expect(captured!.body.tripId).toBeNull()
  })

  it('有 chunk 正文时链接追加在正文后', async () => {
    mockQuery.tripId = '7'
    const { wrapper, cb } = await mountAndSend()

    cb.onChunk('好的，已为您调整。')
    cb.onTripEvent!('trip_modified', { newTripId: 99, summary: 'S' })
    cb.onComplete({ conversationId: 5 })
    await flushPromises()

    expect(wrapper.text()).toContain('好的，已为您调整。')
    expect(wrapper.html()).toContain('/detail?id=99')
  })
})
