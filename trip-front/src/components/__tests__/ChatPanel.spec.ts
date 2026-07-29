import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import ChatPanel from '../ChatPanel.vue'

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
  })

  it('请求体携带 tripId', async () => {
    const { cb } = await mountAndSend(7)
    expect(cb.body.tripId).toBe(7)
  })

  it('收到 trip_modified 事件 → complete 后 emit trip-updated 并回填摘要', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onTripEvent!('trip_modified', { newTripId: 99, parentTripId: 1, summary: '已生成修改版行程' })
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    expect(wrapper.emitted('trip-updated')).toEqual([[99]])
    // AI 气泡回填事件摘要（正文不走 chunk 流）
    const text = wrapper.text()
    expect(text).toContain('已生成修改版行程')
  })

  it('续传重放同一事件 → 只 emit 一次', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onTripEvent!('trip_modified', { newTripId: 99, summary: 'S' })
    cb.onTripEvent!('trip_modified', { newTripId: 99, summary: 'S' })
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    expect(wrapper.emitted('trip-updated')).toEqual([[99]])
  })

  it('有 chunk 正文时不覆盖气泡内容', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onChunk('好的，正在为您修改…')
    cb.onTripEvent!('trip_modified', { newTripId: 99, summary: '已生成修改版行程' })
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    expect(wrapper.emitted('trip-updated')).toEqual([[99]])
    expect(wrapper.text()).toContain('好的，正在为您修改…')
    expect(wrapper.text()).not.toContain('已生成修改版行程')
  })

  it('无 trip_modified 事件 → 不 emit', async () => {
    const { wrapper, cb } = await mountAndSend()

    cb.onChunk('普通回复')
    cb.onComplete({ conversationId: 5 })
    await nextTick()

    expect(wrapper.emitted('trip-updated')).toBeUndefined()
  })
})
