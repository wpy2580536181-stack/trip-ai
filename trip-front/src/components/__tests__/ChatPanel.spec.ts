import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import ChatPanel from '../ChatPanel.vue'

// Node 实验性 localStorage 全局遮蔽 happy-dom 实现，stub 一个内存版
const storageMap = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (k: string) => storageMap.get(k) ?? null,
  setItem: (k: string, v: string) => storageMap.set(k, String(v)),
  removeItem: (k: string) => storageMap.delete(k),
  clear: () => storageMap.clear(),
})

// 会话恢复 API mock（Fix 6）
const mockGetConversation = vi.fn().mockResolvedValue({ data: null })
vi.mock('@/api/conversation', () => ({
  getConversation: (...args: any[]) => mockGetConversation(...args),
}))

// naive-ui useMessage 需要 provider，只 mock 这一个导出，组件保留真实实现
vi.mock('naive-ui', async (importOriginal) => {
  const actual = await importOriginal<typeof import('naive-ui')>()
  return {
    ...actual,
    useMessage: () => ({ error: vi.fn(), success: vi.fn() }),
  }
})

// 捕获 fetchStream 的调用参数与回调
type StreamCallbacks = {
  body: any
  onChunk: (chunk: string) => void
  onComplete: (data?: any) => void
  onError: (err: any) => void
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
      onError: any,
      _onToolEvent: any,
      _onHeartbeat: any,
      _onResume: any,
      options: any,
    ) => {
      captured = { body, onChunk, onComplete, onError, onTripEvent: options?.onTripEvent }
      return Promise.resolve(new AbortController())
    },
  ),
}))

/** 通过 prefill 触发一次自动发送，返回捕获的回调 */
async function mountAndSend(tripId: number | null = 1): Promise<{ wrapper: any; cb: StreamCallbacks }> {
  const wrapper = mount(ChatPanel, { props: { tripId, prefill: '' } })
  await wrapper.setProps({ prefill: '把第2天下午的景点换掉' })
  await nextTick()
  await flushPromises()
  expect(captured).not.toBeNull()
  return { wrapper, cb: captured! }
}

describe('ChatPanel.vue — trip_modified 结构化事件', () => {
  beforeEach(() => {
    captured = null
    vi.clearAllMocks()
    storageMap.clear()
    mockGetConversation.mockResolvedValue({ data: null })
  })

  it('请求体携带 tripId', async () => {
    const { cb } = await mountAndSend(7)
    expect(cb.body.tripId).toBe(7)
  })

  it('收到 trip_diff 事件 → 渲染 Diff 卡片，采纳后 emit trip-updated', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onTripEvent!('trip_diff', {
      newTripId: 99,
      parentTripId: 1,
      changes: [{ day: 2, period: 'afternoon', oldSpot: '旧景点', newSpot: '新景点' }],
    })
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    // 事件到达后不自动切换，先展示 Diff 卡片供用户确认
    expect(wrapper.emitted('trip-updated')).toBeUndefined()
    expect(wrapper.text()).toContain('行程修改建议')
    expect(wrapper.text()).toContain('新景点')

    // 采纳修改方案 → emit trip-updated
    wrapper.vm.onDiffConfirm(99)
    await nextTick()
    expect(wrapper.emitted('trip-updated')).toEqual([[99]])
  })

  it('续传重放同一事件 → 只渲染一张卡片，确认后只 emit 一次', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onTripEvent!('trip_diff', { newTripId: 99, parentTripId: 1, changes: [{ day: 1, period: 'morning', oldSpot: 'A', newSpot: 'B' }] })
    cb.onTripEvent!('trip_diff', { newTripId: 99, parentTripId: 1, changes: [{ day: 1, period: 'morning', oldSpot: 'A', newSpot: 'B' }] })
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    // 同一次会话中重放同一事件：只渲染一张卡片（同 idx 覆盖），确认也只 emit 一次
    wrapper.vm.onDiffConfirm(99)
    await nextTick()
    expect(wrapper.emitted('trip-updated')).toEqual([[99]])
  })

  it('有 chunk 正文时不覆盖气泡内容', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onChunk('好的，正在为您修改…')
    cb.onTripEvent!('trip_diff', { newTripId: 99, parentTripId: 1, changes: [{ day: 2, period: 'afternoon', oldSpot: '旧', newSpot: '新' }] })
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    // Diff 卡片展示，不自动切换、不覆盖 chunk 正文
    expect(wrapper.emitted('trip-updated')).toBeUndefined()
    expect(wrapper.text()).toContain('好的，正在为您修改…')
    expect(wrapper.text()).toContain('行程修改建议')
    wrapper.vm.onDiffConfirm(99)
    await nextTick()
    expect(wrapper.emitted('trip-updated')).toEqual([[99]])
  })

  it('无 trip_modified 事件 → 不 emit', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onChunk('普通回复')
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    expect(wrapper.emitted('trip-updated')).toBeUndefined()
  })
})

describe('ChatPanel.vue — 修改窗口期竞态防护（Fix 4）', () => {
  beforeEach(() => {
    captured = null
    vi.clearAllMocks()
    storageMap.clear()
    mockGetConversation.mockResolvedValue({ data: null })
  })

  it('trip-updated 后立即再发消息 → 被拦截；tripId 变化后恢复', async () => {
    const { wrapper, cb } = await mountAndSend(1)

    cb.onTripEvent!('trip_diff', { newTripId: 99, parentTripId: 1, changes: [{ day: 2, period: 'afternoon', oldSpot: '旧', newSpot: '新' }] })
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    // 采纳修改方案 → emit trip-updated 并进入窗口期
    wrapper.vm.onDiffConfirm(99)
    await nextTick()
    expect(wrapper.emitted('trip-updated')).toEqual([[99]])

    // 窗口期内发消息：不应发起请求
    captured = null
    wrapper.vm.inputMessage = '再改一下'
    wrapper.vm.sendMessage()
    await flushPromises()
    expect(captured).toBeNull()

    // 父组件刷新完成（tripId 切到新版本）后恢复可发
    await wrapper.setProps({ tripId: 99 })
    wrapper.vm.inputMessage = '再改一下'
    wrapper.vm.sendMessage()
    await flushPromises()
    expect(captured).not.toBeNull()
    expect(captured!.body.tripId).toBe(99)
  })

  it('disabled prop 为 true → 拦截发送', async () => {
    const wrapper = mount(ChatPanel, { props: { tripId: 1, prefill: '', disabled: true } })
    wrapper.vm.inputMessage = '你好'
    wrapper.vm.sendMessage()
    await flushPromises()
    expect(captured).toBeNull()
  })
})

describe('ChatPanel.vue — 会话持久化（Fix 6）', () => {
  beforeEach(() => {
    captured = null
    vi.clearAllMocks()
    storageMap.clear()
    mockGetConversation.mockResolvedValue({ data: null })
  })

  it('挂载时有存量 key → 恢复会话与历史消息，后续请求带恢复的 conversationId', async () => {
    storageMap.set('trip_panel_conv_7', '42')
    mockGetConversation.mockResolvedValue({
      data: {
        id: 42,
        messages: [
          { id: 1, role: 'user', content: '之前的提问', createdAt: '2026-07-29T10:00:00Z' },
          { id: 2, role: 'assistant', content: '之前的回答', createdAt: '2026-07-29T10:00:05Z' },
        ],
      },
    })

    const wrapper = mount(ChatPanel, { props: { tripId: 7, prefill: '' } })
    await flushPromises()

    expect(mockGetConversation).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('之前的提问')
    expect(wrapper.text()).toContain('之前的回答')

    wrapper.vm.inputMessage = '继续问'
    wrapper.vm.sendMessage()
    await flushPromises()
    expect(captured!.body.conversationId).toBe(42)
  })

  it('会话已删除（接口报错）→ 清 key，从空会话开始', async () => {
    storageMap.set('trip_panel_conv_7', '42')
    mockGetConversation.mockRejectedValue(new Error('404'))

    const wrapper = mount(ChatPanel, { props: { tripId: 7, prefill: '' } })
    await flushPromises()

    expect(storageMap.has('trip_panel_conv_7')).toBe(false)
    expect(wrapper.vm.messages.length).toBe(0)
  })

  it('complete 后持久化 conversationId 到 tripId 维度的 key', async () => {
    const { cb } = await mountAndSend(7)
    cb.onComplete({ conversationId: 55 })
    await nextTick()

    expect(storageMap.get('trip_panel_conv_7')).toBe('55')
  })

  it('tripId 切换（版本升级）→ 会话 ID 迁移到新 key', async () => {
    const { wrapper, cb } = await mountAndSend(7)
    cb.onComplete({ conversationId: 55 })
    await nextTick()

    await wrapper.setProps({ tripId: 99 })
    expect(storageMap.get('trip_panel_conv_99')).toBe('55')
  })

  it('无 tripId → 不尝试恢复也不持久化', async () => {
    storageMap.set('trip_panel_conv_7', '42')
    const { cb } = await mountAndSend(null)
    cb.onComplete({ conversationId: 55 })
    await nextTick()

    expect(mockGetConversation).not.toHaveBeenCalled()
    expect([...storageMap.keys()]).toEqual(['trip_panel_conv_7'])
  })
})
