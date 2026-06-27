/**
 * summaryService 纯函数单测
 *
 * 当前覆盖 selectCompactionRange：
 * - 不需要压缩（total ≤ target）→ 返回 toCompact=[]
 * - 正常压缩：从最老贪心累加
 * - 边界：单条超 target
 * - 边界：整除 / 凑不够释放量
 * - 边界：空数组
 */

import { describe, it, expect } from 'vitest'
import { selectCompactionRange } from '../summaryService'

function msg(id: number, content: string) {
  return { id, content }
}

// 300 中文字符 = 200 token
const token200 = '中'.repeat(300)

describe('selectCompactionRange', () => {
  it('空消息：toCompact 为空', () => {
    const r = selectCompactionRange([], 0, 12000)
    expect(r.toCompact).toEqual([])
    expect(r.toKeep).toEqual([])
    expect(r.freedTokens).toBe(0)
  })

  it('total ≤ target：不压缩', () => {
    const messages = [msg(1, token200), msg(2, token200)]  // 400 token
    const r = selectCompactionRange(messages, 400, 12000)
    expect(r.toCompact).toEqual([])
    expect(r.toKeep).toEqual(messages)
    expect(r.freedTokens).toBe(0)
  })

  it('total = target：不压缩（边界，> 不是 >=）', () => {
    const r = selectCompactionRange([msg(1, token200)], 200, 200)
    expect(r.toCompact).toEqual([])
  })

  it('正常压缩：从最老贪心累加', () => {
    // 5 条 × 200 token = 1000，target=400，需要释放 600
    // 累加：200(1) + 200(2) + 200(3) = 600 → 压缩 3 条
    const messages = [
      msg(1, token200),
      msg(2, token200),
      msg(3, token200),
      msg(4, token200),
      msg(5, token200),
    ]
    const r = selectCompactionRange(messages, 1000, 400)
    expect(r.toCompact.map(m => m.id)).toEqual([1, 2, 3])
    expect(r.toKeep.map(m => m.id)).toEqual([4, 5])
    expect(r.freedTokens).toBe(600)
  })

  it('压缩量不均：从最老开始，凑够即停', () => {
    // msgs: 100, 50, 300, 200, 150 → 总额 800
    // target 400 → 释放 400
    // 累加：100+50+300 = 450 ≥ 400 → 压缩 3 条
    const m1 = msg(1, '中'.repeat(150))   // 100 token
    const m2 = msg(2, '中'.repeat(75))    // 50 token
    const m3 = msg(3, '中'.repeat(450))   // 300 token
    const m4 = msg(4, '中'.repeat(300))   // 200 token
    const m5 = msg(5, '中'.repeat(225))   // 150 token
    const r = selectCompactionRange([m1, m2, m3, m4, m5], 800, 400)
    expect(r.toCompact.map(x => x.id)).toEqual([1, 2, 3])
    expect(r.freedTokens).toBe(450)
  })

  it('单条消息就超过 target：至少压缩 1 条', () => {
    // 1 条 20000 token，target=12000，需要释放 8000
    // 累加 1 条就够，但仍应压缩 1 条（边界保护）
    const m1 = msg(1, '中'.repeat(30000))  // 20000 token
    const r = selectCompactionRange([m1], 20000, 12000)
    expect(r.toCompact.map(x => x.id)).toEqual([1])
    expect(r.toKeep).toEqual([])
  })

  it('所有消息合起来才刚好够：全部压缩', () => {
    const messages = [msg(1, token200), msg(2, token200)]
    // total=400, target=0, 需释放 400
    const r = selectCompactionRange(messages, 400, 0)
    expect(r.toCompact.length).toBeGreaterThanOrEqual(1)
    expect(r.toKeep.length + r.toCompact.length).toBe(messages.length)
  })
})
