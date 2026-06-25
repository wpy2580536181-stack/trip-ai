import { describe, it, expect, beforeEach, vi } from 'vitest'
import { TraceRecorder } from '../agent/traceRecorder'

const mockCreateMany = vi.fn()
vi.mock('../../config/database', () => ({
  default: {
    agentStep: {
      createMany: (...args: any[]) => mockCreateMany(...args),
    },
  },
}))

describe('TraceRecorder', () => {
  beforeEach(() => {
    mockCreateMany.mockReset()
    mockCreateMany.mockResolvedValue({ count: 0 })
  })

  it('add() 累积 step 到 buffer', () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_start', name: 'retrieve_knowledge' })
    r.add({ step: 2, type: 'tool_end', name: 'retrieve_knowledge', output: '5 POIs', durationMs: 1234 })
    expect(r.getSteps()).toHaveLength(2)
  })

  it('flush() 空 buffer 不调 createMany', async () => {
    const r = new TraceRecorder(847)
    await r.flush()
    expect(mockCreateMany).not.toHaveBeenCalled()
  })

  it('flush() 调 createMany 一次传所有 step', async () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_start', name: 'retrieve_knowledge', args: { city: '北京' } })
    r.add({ step: 2, type: 'tool_end', name: 'retrieve_knowledge', output: '5 POIs', durationMs: 1234 })
    r.add({ step: 3, type: 'complete', durationMs: 4500 })
    await r.flush()
    expect(mockCreateMany).toHaveBeenCalledTimes(1)
    expect(mockCreateMany.mock.calls[0][0].data).toHaveLength(3)
    expect(mockCreateMany.mock.calls[0][0].data[0]).toMatchObject({
      messageId: 847,
      step: 1,
      type: 'tool_start',
      name: 'retrieve_knowledge',
      args: { city: '北京' },
    })
  })

  it('args null 时不传 args 字段', async () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'chunk' })
    await r.flush()
    expect(mockCreateMany.mock.calls[0][0].data[0].args).toBeNull()
  })

  it('flush 失败只 warn，不抛错', async () => {
    mockCreateMany.mockRejectedValue(new Error('DB down'))
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_start' })
    await expect(r.flush()).resolves.toBeUndefined()
  })

  it('output 截断由调用方负责，recorder 透传', async () => {
    const r = new TraceRecorder(847)
    r.add({ step: 1, type: 'tool_end', output: 'a'.repeat(15000) })
    await r.flush()
    expect(mockCreateMany.mock.calls[0][0].data[0].output).toBe('a'.repeat(15000))
  })
})
