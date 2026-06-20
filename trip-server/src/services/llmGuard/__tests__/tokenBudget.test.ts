import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { TokenBudgetManager } from '../tokenBudget'

describe('TokenBudgetManager', () => {
  let manager: TokenBudgetManager

  beforeEach(() => {
    manager = new TokenBudgetManager({
      userTokenLimit: 1000,
      globalTokenLimit: 5000,
      userWindowMs: 60_000,
      globalWindowMs: 60_000,
    })
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-01-01T00:00:00Z'))
  })

  afterEach(() => {
    manager.shutdown()
    vi.useRealTimers()
  })

  it('首次查询返回零用量且允许通过', () => {
    const stats = manager.checkUserBudget('user1')
    expect(stats.allowed).toBe(true)
    expect(stats.current).toBe(0)
    expect(stats.limit).toBe(1000)
  })

  it('记录用量后累加且未超限时允许通过', async () => {
    await manager.recordUserUsage('user1', 800)
    const stats = manager.checkUserBudget('user1')
    expect(stats.current).toBe(800)
    expect(stats.allowed).toBe(true)
  })

  it('超过用户额度后拒绝', async () => {
    await manager.recordUserUsage('user1', 1001)
    const stats = manager.checkUserBudget('user1')
    expect(stats.allowed).toBe(false)
    expect(stats.current).toBe(1001)
  })

  it('窗口过期后用量重置为0并允许通过', async () => {
    await manager.recordUserUsage('user1', 1001)
    expect(manager.checkUserBudget('user1').allowed).toBe(false)

    vi.advanceTimersByTime(61_000)
    const stats = manager.checkUserBudget('user1')
    expect(stats.current).toBe(0)
    expect(stats.allowed).toBe(true)
  })
})
