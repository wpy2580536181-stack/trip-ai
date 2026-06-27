/**
 * stream-parser 单元测试（node:test，零依赖）
 *
 * 覆盖：
 *  - parseSSEEvent: 单条 SSE 解析
 *  - SSEParser.feed: 流式累加（chunk 边界）
 *  - id: 字段提取（用作 Last-Event-ID）
 *  - event: end 识别
 *  - 容错：JSON 失败、缺失字段
 *  - getBackoffMs: 退避时间
 */

import { test, describe } from 'node:test'
import assert from 'node:assert/strict'
import { parseSSEEvent, SSEParser, getBackoffMs } from '../stream-parser.ts'

describe('parseSSEEvent', () => {
  test('解析 data: 字段（JSON 形式）', () => {
    const ev = parseSSEEvent('data: {"type":"chunk","content":"hi"}')
    assert.equal(ev?.type, 'chunk')
    assert.equal(ev?.content, 'hi')
  })

  test('解析 id: 字段（数字）', () => {
    const ev = parseSSEEvent('id: 42\ndata: {"type":"chunk","content":"x"}')
    assert.equal(ev?.id, 42)
  })

  test('解析 event: end', () => {
    const ev = parseSSEEvent('event: end\ndata: {"done":true}')
    // event 不映射到 type，识别用 sentinel
    assert.equal(ev?.isEnd, true)
  })

  test('空行 / 无效行 跳过', () => {
    assert.equal(parseSSEEvent(''), null)
    assert.equal(parseSSEEvent('   \n\n'), null)
    assert.equal(parseSSEEvent(':comment'), null)
  })

  test('JSON 解析失败返回 null（不抛错）', () => {
    const ev = parseSSEEvent('data: {garbage')
    assert.equal(ev, null)
  })

  test('多行 data 拼接（字符串值内含换行）', () => {
    // SSE 允许多行 data 拼接，但现代 JSON.parse 拒绝裸换行符
    // 实际场景罕见：测试拼接逻辑正常即可
    const ev = parseSSEEvent('data: line1\ndata: line2')
    // dataLines = ['line1', 'line2']，join = 'line1\nline2'（不是 JSON）
    // JSON.parse 失败 → 返回 null（不应抛错）
    assert.equal(ev, null)
  })

  test('tool_start/tool_end 解析', () => {
    const a = parseSSEEvent('data: {"type":"tool_start","name":"get_weather"}')
    assert.equal(a?.type, 'tool_start')
    assert.equal(a?.name, 'get_weather')
  })

  test('error 事件解析（后端用 "error" 字段，不是 "content"）', () => {
    const ev = parseSSEEvent('data: {"type":"error","error":"推荐失败：budget 非法"}')
    assert.equal(ev?.type, 'error')
    assert.equal(ev?.error, '推荐失败：budget 非法')
    // 旧 fallback 路径：消费者从 ev.error 读取，不能用 ev.content（undefined）
    assert.equal(ev?.content, undefined)
  })
})

describe('SSEParser', () => {
  test('单 chunk 完整事件', () => {
    const p = new SSEParser()
    const events = p.feed('data: {"type":"chunk","content":"a"}\n\n')
    assert.equal(events.length, 1)
    assert.equal(events[0].type, 'chunk')
    assert.equal(events[0].content, 'a')
  })

  test('chunk 边界切分（事件跨 chunk）', () => {
    const p = new SSEParser()
    const e1 = p.feed('id: 1\ndata: {"type":')
    assert.equal(e1.length, 0) // buffer 不够解析
    const e2 = p.feed('"chunk","content":"x"}\n\n')
    assert.equal(e2.length, 1)
    assert.equal(e2[0].id, 1)
    assert.equal(e2[0].content, 'x')
  })

  test('多事件连续', () => {
    const p = new SSEParser()
    const e = p.feed(
      'id: 1\ndata: {"type":"chunk","content":"a"}\n\n' +
        'id: 2\ndata: {"type":"chunk","content":"b"}\n\n' +
        'event: end\ndata: {"done":true}\n\n'
    )
    assert.equal(e.length, 3)
    assert.equal(e[0].id, 1)
    assert.equal(e[1].id, 2)
    assert.equal(e[2].isEnd, true)
  })

  test('损坏事件跳过，后续仍解析', () => {
    const p = new SSEParser()
    const e = p.feed(
      'data: {garbage\n\n' +
        'data: {"type":"chunk","content":"ok"}\n\n'
    )
    assert.equal(e.length, 1)
    assert.equal(e[0].content, 'ok')
  })

  test('reset 清空 buffer', () => {
    const p = new SSEParser()
    p.feed('data: {"type":')
    p.reset()
    // 第二段是合法 SSE（完整 data: + JSON + \n\n）
    const e = p.feed('data: {"type":"chunk","content":"fresh"}\n\n')
    assert.equal(e.length, 1)
    assert.equal(e[0].content, 'fresh')
  })

  test('不完整尾部不输出（等下个 chunk）', () => {
    const p = new SSEParser()
    const e = p.feed('id: 5\ndata: {"type":"chunk","content":')
    assert.equal(e.length, 0) // 没换行符 \n\n
  })
})

describe('getBackoffMs', () => {
  test('attempt=1 → 1s', () => assert.equal(getBackoffMs(1), 1000))
  test('attempt=2 → 2s', () => assert.equal(getBackoffMs(2), 2000))
  test('attempt=3 → 4s', () => assert.equal(getBackoffMs(3), 4000))
  test('attempt=4 → 8s', () => assert.equal(getBackoffMs(4), 8000))
  test('attempt=5 → 16s（封顶）', () => assert.equal(getBackoffMs(5), 16000))
  test('attempt=10 → 仍 16s', () => assert.equal(getBackoffMs(10), 16000))
})
