import { describe, it, beforeEach, expect, vi } from 'vitest'
import * as amapGuards from '../amapGuards'
import * as amapMcpClient from '../amapMcpClient'

describe('amapGuards', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    amapGuards.resetCircuit()
    amapGuards.clearCache()
  })

  it('should return cached result on repeated call', async () => {
    let callCount = 0
    vi.spyOn(amapMcpClient, 'callTool').mockImplementation(() => {
      callCount++
      return Promise.resolve('weather: 晴')
    })

    const r1 = await amapGuards.call('maps_weather', { city: '北京' }, { cacheTtlMs: 60000 })
    expect(r1).toBe('weather: 晴')
    expect(callCount).toBe(1)

    const r2 = await amapGuards.call('maps_weather', { city: '北京' }, { cacheTtlMs: 60000 })
    expect(r2).toBe('weather: 晴')
    expect(callCount, 'should use cache').toBe(1)
  })

  it('should throw RATE_LIMITED when bucket empty', async () => {
    const promises = []
    for (let i = 0; i < 10; i++) {
      promises.push(amapGuards.call('amap_weather', { city: '北京' }, { cacheTtlMs: 0 }))
    }
    const results = await Promise.allSettled(promises)
    const rejected = results.filter(r => r.status === 'rejected')
    expect(rejected.length).toBeGreaterThan(0)
    const reasons = rejected.map(r => (r as PromiseRejectedResult).reason.message)
    expect(reasons.some(m => m.includes('RATE_LIMITED'))).toBeTruthy()
  })

  it('should throw CIRCUIT_OPEN after repeated failures', async () => {
    vi.spyOn(amapMcpClient, 'callTool').mockImplementation(() => Promise.reject(new Error('mcp error')))

    let gotCircuitOpen = false
    for (let i = 0; i < 30; i++) {
      try {
        await amapGuards.call(`fail_test_${i}`, {}, { cacheTtlMs: 0 })
      } catch (e) {
        if ((e as Error).message === 'AMAP_MCP_CIRCUIT_OPEN') {
          gotCircuitOpen = true
          break
        }
      }
    }
    expect(gotCircuitOpen).toBeTruthy()
  })
})
