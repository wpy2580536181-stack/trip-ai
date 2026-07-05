/**
 * stream-parser 单元测试（Vitest 版本）
 *
 * 覆盖：
 *  - parseSSEEvent: 单条 SSE 解析
 *  - SSEParser.feed: 流式累加（chunk 边界）
 *  - id: 字段提取（用作 Last-Event-ID）
 *  - event: end 识别
 *  - 容错：JSON 失败、缺失字段
 *  - getBackoffMs: 退避时间
 */

import { describe, it, expect } from 'vitest'
import { parseSSEEvent, SSEParser, getBackoffMs } from '../stream-parser'

describe('parseSSEEvent', () => {
  it('解析 data: 字段（JSON 形式）', () => {
    const ev = parseSSEEvent('data: {"type":"chunk","content":"hi"}')
    expect(ev?.type).toBe('chunk')
    expect(ev?.content).toBe('hi')
  })

  it('解析 id: 字段（数字）', () => {
    const ev = parseSSEEvent('id: 42\ndata: {"type":"chunk","content":"x"}')
    expect(ev?.id).toBe(42)
  })

  it('解析 event: end', () => {
    const ev = parseSSEEvent('event: end\ndata: {"done":true}')
    expect(ev?.isEnd).toBe(true)
  })

  it('空行 / 无效行 跳过', () => {
    expect(parseSSEEvent('')).toBeNull()
    expect(parseSSEEvent('   \n\n')).toBeNull()
    expect(parseSSEEvent(':comment')).toBeNull()
  })

  it('JSON 解析失败返回 null（不抛错）', () => {
    const ev = parseSSEEvent('data: {garbage')
    expect(ev).toBeNull()
  })

  it('tool_start/tool_end 解析', () => {
    const a = parseSSEEvent('data: {"type":"tool_start","name":"get_weather"}')
    expect(a?.type).toBe('tool_start')
    expect(a?.name).toBe('get_weather')
  })

  it('error 事件解析（后端用 "error" 字段）', () => {
    const ev = parseSSEEvent('data: {"type":"error","error":"推荐失败"}')
    expect(ev?.type).toBe('error')
    expect(ev?.error).toBe('推荐失败')
    expect(ev?.content).toBeUndefined()
  })
})

describe('SSEParser', () => {
  it('单 chunk 完整事件', () => {
    const p = new SSEParser()
    const events = p.feed('data: {"type":"chunk","content":"a"}\n\n')
    expect(events).toHaveLength(1)
    expect(events[0].content).toBe('a')
  })

  it('chunk 边界切分（事件跨 chunk）', () => {
    const p = new SSEParser()
    const e1 = p.feed('id: 1\ndata: {"type":')
    expect(e1).toHaveLength(0)
    const e2 = p.feed('"chunk","content":"x"}\n\n')
    expect(e2).toHaveLength(1)
    expect(e2[0].id).toBe(1)
    expect(e2[0].content).toBe('x')
  })

  it('多事件连续', () => {
    const p = new SSEParser()
    const e = p.feed(
      'id: 1\ndata: {"type":"chunk","content":"a"}\n\n' +
      'id: 2\ndata: {"type":"chunk","content":"b"}\n\n' +
      'event: end\ndata: {"done":true}\n\n'
    )
    expect(e).toHaveLength(3)
    expect(e[0].id).toBe(1)
    expect(e[1].id).toBe(2)
    expect(e[2].isEnd).toBe(true)
  })

  it('损坏事件跳过，后续仍解析', () => {
    const p = new SSEParser()
    const e = p.feed(
      'data: {garbage\n\n' +
      'data: {"type":"chunk","content":"ok"}\n\n'
    )
    expect(e).toHaveLength(1)
    expect(e[0].content).toBe('ok')
  })

  it('reset 清空 buffer', () => {
    const p = new SSEParser()
    p.feed('data: {"type":')
    p.reset()
    const e = p.feed('data: {"type":"chunk","content":"fresh"}\n\n')
    expect(e).toHaveLength(1)
    expect(e[0].content).toBe('fresh')
  })

  it('不完整尾部不输出（等下个 chunk）', () => {
    const p = new SSEParser()
    const e = p.feed('id: 5\ndata: {"type":"chunk","content":')
    expect(e).toHaveLength(0)
  })
})

describe('getBackoffMs', () => {
  it('attempt=1 返回 1s', () => expect(getBackoffMs(1)).toBe(1000))
  it('attempt=2 返回 2s', () => expect(getBackoffMs(2)).toBe(2000))
  it('attempt=3 返回 4s', () => expect(getBackoffMs(3)).toBe(4000))
  it('attempt=4 返回 8s', () => expect(getBackoffMs(4)).toBe(8000))
  it('attempt=5 到达封顶 16s', () => expect(getBackoffMs(5)).toBe(16000))
  it('attempt=10 仍为 16s', () => expect(getBackoffMs(10)).toBe(16000))
})
