/**
 * ToolCache 单元测试
 *
 * 覆盖：
 * - getOrCompute 命中/未命中
 * - 字面 key 归一化：trim + lowercase + 排序 keys
 * - embedding 归一化：相似 query 命中、阈值边界
 * - compute 失败时不写入缓存
 * - 未配置的 tool 直接调 compute
 * - 不同 tool 的 key namespace 隔离
 */

import { describe, it, expect, vi } from 'vitest'

// Mock logger（避免 log.info 副作用）
vi.mock('../../utils/logger', () => ({
  agentLog: { info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() },
}))

// Mock embeddings（避免 bge 模型懒加载）
vi.mock('../../config/embeddings', () => ({
  embedText: vi.fn(),
}))

import { ToolCache } from '../toolCache'

/**
 * Deterministic mock embedder：基于"语义关键词"返回固定向量。
 * 让我们能精确控制哪些 query 之间相似、哪些不相似。
 *
 * 向量设计（4 维）：
 * - [0.95, 0.31, 0, 0] = "成都+美食类"（美食/好吃/川菜/小吃）
 * - [0.31, 0.95, 0, 0] = "成都+景点类"（景点/必去/历史文化）
 * - [0, 0, 1, 0] = "北京"
 * - [0, 0, 0, 1] = "其他"
 *
 * 两两 cosine sim（已 L2 normalize，sim = dot）：
 * - 美食 vs 美食 = 1.0
 * - 美食 vs 好吃 = 1.0（同向量）
 * - 美食 vs 景点 = 0.95*0.31 + 0.31*0.95 = 0.589
 * - 美食 vs 北京 = 0
 */
function makeMockEmbedder(): (text: string) => Promise<number[]> {
  return async (text: string) => {
    if (text.includes('成都') && (text.includes('food') || text.includes('美食') || text.includes('好吃') || text.includes('川菜') || text.includes('小吃'))) {
      return [0.95, 0.31, 0, 0]
    }
    if (text.includes('成都') && (text.includes('景点') || text.includes('必去') || text.includes('历史文化') || text.includes('亲子'))) {
      return [0.31, 0.95, 0, 0]
    }
    if (text.includes('北京')) {
      return [0, 0, 1, 0]
    }
    return [0, 0, 0, 1]
  }
}

describe('ToolCache', () => {
  it('首次调用：miss，compute 并写入', async () => {
    const cache = new ToolCache({ get_weather: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('sunny 25°C')

    const r = await cache.getOrCompute('get_weather', { city: '成都' }, compute)

    expect(r.hit).toBe(false)
    expect(r.result).toBe('sunny 25°C')
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('相同 key 再次调用：hit，不再 compute', async () => {
    const cache = new ToolCache({ get_weather: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('sunny 25°C')

    await cache.getOrCompute('get_weather', { city: '成都' }, compute)
    const r = await cache.getOrCompute('get_weather', { city: '成都' }, compute)

    expect(r.hit).toBe(true)
    expect(r.result).toBe('sunny 25°C')
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('key 归一化：trim 和 lowercase 让字面不同视为相同', async () => {
    const cache = new ToolCache({ get_weather: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('sunny')

    await cache.getOrCompute('get_weather', { city: '成都' }, compute)
    // 同样的城市，trim + lowercase 后视为相同
    const r = await cache.getOrCompute('get_weather', { city: '  成都  ' }, compute)

    expect(r.hit).toBe(true)
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('key 归一化：string 字段 lowercase 视为相同', async () => {
    const cache = new ToolCache({ retrieve_knowledge: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('result')

    await cache.getOrCompute('retrieve_knowledge', { query: 'CHENGDU', city: '北京' }, compute)
    const r = await cache.getOrCompute('retrieve_knowledge', { query: 'chengdu', city: '北京' }, compute)

    expect(r.hit).toBe(true)
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('key 归一化：排序 keys 让 {a, b} = {b, a}', async () => {
    const cache = new ToolCache({ get_weather: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('result')

    await cache.getOrCompute('get_weather', { city: '成都', date: '2026-06-27' }, compute)
    const r = await cache.getOrCompute('get_weather', { date: '2026-06-27', city: '成都' }, compute)

    expect(r.hit).toBe(true)
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('key 归一化：跳过 undefined / null 字段', async () => {
    const cache = new ToolCache({ search_hotels: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('hotel result')

    await cache.getOrCompute('search_hotels', { city: '北京', budget: undefined, level: null }, compute)
    const r = await cache.getOrCompute('search_hotels', { city: '北京' }, compute)

    expect(r.hit).toBe(true)
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('key 归一化：数字/boolean 字段不同视为不同 key', async () => {
    const cache = new ToolCache({ search_hotels: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('hotel result')

    await cache.getOrCompute('search_hotels', { city: '北京', budget: 500 }, compute)
    const r = await cache.getOrCompute('search_hotels', { city: '北京', budget: 800 }, compute)

    expect(r.hit).toBe(false)
    expect(compute).toHaveBeenCalledTimes(2)
  })

  it('compute 失败：不写入缓存，下次重新调', async () => {
    const cache = new ToolCache({ get_weather: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn()
      .mockRejectedValueOnce(new Error('wttr.in 500'))
      .mockResolvedValueOnce('sunny 25°C')

    await expect(cache.getOrCompute('get_weather', { city: '成都' }, compute)).rejects.toThrow('wttr.in 500')
    const r = await cache.getOrCompute('get_weather', { city: '成都' }, compute)

    expect(r.hit).toBe(false)  // 上次失败没写
    expect(r.result).toBe('sunny 25°C')
    expect(compute).toHaveBeenCalledTimes(2)
  })

  it('未配置的 tool：直接调 compute，不写缓存', async () => {
    const cache = new ToolCache({ get_weather: { ttlMs: 60_000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('distance result')

    const r1 = await cache.getOrCompute('calculate_distance', { from: '北京', to: '上海' }, compute)
    const r2 = await cache.getOrCompute('calculate_distance', { from: '北京', to: '上海' }, compute)

    expect(r1.hit).toBe(false)
    expect(r2.hit).toBe(false)
    expect(compute).toHaveBeenCalledTimes(2)  // 每次都调
  })

  it('不同 tool 的 key namespace 隔离', async () => {
    const cache = new ToolCache({
      get_weather: { ttlMs: 60_000, maxSize: 10 },
      retrieve_knowledge: { ttlMs: 60_000, maxSize: 10 },
    })

    // "成都" 在 weather 和 knowledge 里语义不同
    await cache.getOrCompute('get_weather', { city: '成都' }, async () => 'weather:成都 sunny')
    const r = await cache.getOrCompute('retrieve_knowledge', { city: '成都' }, async () => 'knowledge:成都景点列表')

    expect(r.result).toBe('knowledge:成都景点列表')  // 不会命中 weather 的缓存
  })

  it('TTL 过期：重新调 compute', async () => {
    vi.useFakeTimers()
    const cache = new ToolCache({ get_weather: { ttlMs: 1000, maxSize: 10 } })
    const compute = vi.fn().mockResolvedValue('sunny')

    await cache.getOrCompute('get_weather', { city: '成都' }, compute)
    expect(compute).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(2000)  // 2s > 1s TTL
    const r = await cache.getOrCompute('get_weather', { city: '成都' }, compute)

    expect(r.hit).toBe(false)
    expect(compute).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })
})

// ============================================================
// Embedding 归一化路径
// ============================================================

describe('ToolCache - embedding 归一化', () => {
  const mockEmbedder = makeMockEmbedder()

  it('embedding 路径：相似 query 命中（成都美食 ≈ 成都好吃）', async () => {
    const cache = new ToolCache({
      retrieve_knowledge: {
        ttlMs: 60_000,
        maxSize: 100,
        embeddingKey: {
          extractor: (a) => `${a.city} ${a.category} ${a.query}`,
          threshold: 0.85,
          embedder: mockEmbedder,
        },
      },
    })
    const compute = vi.fn()
      .mockResolvedValueOnce('result: 成都美食列表')
      .mockResolvedValueOnce('result: 成都好吃的列表（不应被调）')

    await cache.getOrCompute('retrieve_knowledge',
      { city: '成都', category: 'food', query: '美食' }, compute)
    const r = await cache.getOrCompute('retrieve_knowledge',
      { city: '成都', category: 'food', query: '好吃的' }, compute)

    expect(r.hit).toBe(true)
    expect(r.result).toBe('result: 成都美食列表')
    expect(compute).toHaveBeenCalledTimes(1)  // 第二次走 cache
  })

  it('embedding 路径：不同主题不命中（成都美食 vs 成都景点）', async () => {
    const cache = new ToolCache({
      retrieve_knowledge: {
        ttlMs: 60_000,
        maxSize: 100,
        embeddingKey: {
          extractor: (a) => `${a.city} ${a.category} ${a.query}`,
          threshold: 0.85,
          embedder: mockEmbedder,
        },
      },
    })
    const compute = vi.fn()
      .mockResolvedValueOnce('result: 成都美食')
      .mockResolvedValueOnce('result: 成都景点')

    await cache.getOrCompute('retrieve_knowledge',
      { city: '成都', category: 'food', query: '美食' }, compute)
    const r = await cache.getOrCompute('retrieve_knowledge',
      { city: '成都', category: 'attraction', query: '景点' }, compute)

    // 美食 vs 景点 sim = 0.589 < 0.85，不命中
    expect(r.hit).toBe(false)
    expect(r.result).toBe('result: 成都景点')
    expect(compute).toHaveBeenCalledTimes(2)
  })

  it('embedding 路径：跨城市不命中（成都美食 vs 北京美食）', async () => {
    const cache = new ToolCache({
      retrieve_knowledge: {
        ttlMs: 60_000,
        maxSize: 100,
        embeddingKey: {
          extractor: (a) => `${a.city} ${a.category} ${a.query}`,
          threshold: 0.85,
          embedder: mockEmbedder,
        },
      },
    })
    const compute = vi.fn()
      .mockResolvedValueOnce('result: 成都美食')
      .mockResolvedValueOnce('result: 北京美食')

    await cache.getOrCompute('retrieve_knowledge',
      { city: '成都', category: 'food', query: '美食' }, compute)
    const r = await cache.getOrCompute('retrieve_knowledge',
      { city: '北京', category: 'food', query: '美食' }, compute)

    // 成都 vs 北京 sim = 0，正交不命中
    expect(r.hit).toBe(false)
    expect(r.result).toBe('result: 北京美食')
    expect(compute).toHaveBeenCalledTimes(2)
  })

  it('embedding 路径：阈值边界（sim 刚好等于 threshold 命中）', async () => {
    // 构造一对 sim=0.85 的 unit vector：
    // a = [1, 0], b = [0.85, 0.527]，dot = 0.85
    const exactEmbedder = async (_text: string) => {
      if (_text === 'first') return [1, 0]
      if (_text === 'second') return [0.85, 0.527]
      return [1, 0]
    }
    const cache = new ToolCache({
      test: {
        ttlMs: 60_000,
        maxSize: 10,
        embeddingKey: { extractor: () => 'first', threshold: 0.85, embedder: exactEmbedder as any },
      },
    })
    const compute = vi.fn().mockResolvedValue('result')

    await cache.getOrCompute('test', { q: 'first' }, compute)
    // 换 extractor 让第二次送 'second' 进 embedder（拿到不同向量）
    ;(cache as any).configs.get('test').embeddingKey.extractor = () => 'second'
    const r = await cache.getOrCompute('test', { q: 'second' }, compute)

    expect(r.hit).toBe(true)
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('embedding 路径：阈值上调，sim 0.85 变成不命中', async () => {
    const pairEmbedder = async (text: string) => {
      if (text === 'a') return [1, 0]
      if (text === 'b') return [0.85, 0.527]  // sim with 'a' = 0.85
      return [1, 0]
    }
    const cache1 = new ToolCache({
      test: {
        ttlMs: 60_000, maxSize: 10,
        embeddingKey: { extractor: (a: any) => a.q, threshold: 0.85, embedder: pairEmbedder as any },
      },
    })
    const cache2 = new ToolCache({
      test: {
        ttlMs: 60_000, maxSize: 10,
        embeddingKey: { extractor: (a: any) => a.q, threshold: 0.86, embedder: pairEmbedder as any },
      },
    })
    const compute = vi.fn().mockResolvedValue('r')

    await cache1.getOrCompute('test', { q: 'a' }, compute)
    const r1 = await cache1.getOrCompute('test', { q: 'b' }, compute)
    expect(r1.hit).toBe(true)  // sim=0.85, threshold=0.85, 命中

    await cache2.getOrCompute('test', { q: 'a' }, compute)
    const r2 = await cache2.getOrCompute('test', { q: 'b' }, compute)
    expect(r2.hit).toBe(false)  // sim=0.85, threshold=0.86, 不命中
  })

  it('embedding 路径：空 cache 直接 miss', async () => {
    const cache = new ToolCache({
      retrieve_knowledge: {
        ttlMs: 60_000, maxSize: 100,
        embeddingKey: { extractor: () => 'x', threshold: 0.85, embedder: mockEmbedder },
      },
    })
    const compute = vi.fn().mockResolvedValue('result')

    const r = await cache.getOrCompute('retrieve_knowledge', { city: '成都' }, compute)

    expect(r.hit).toBe(false)
    expect(compute).toHaveBeenCalledTimes(1)
  })

  it('embedding 路径：compute 失败时不写 cache', async () => {
    const cache = new ToolCache({
      test: {
        ttlMs: 60_000, maxSize: 10,
        embeddingKey: { extractor: () => 'x', threshold: 0.85, embedder: mockEmbedder },
      },
    })
    const compute = vi.fn()
      .mockRejectedValueOnce(new Error('RAG fail'))
      .mockResolvedValueOnce('result')

    await expect(cache.getOrCompute('test', { q: 'a' }, compute)).rejects.toThrow('RAG fail')
    const r = await cache.getOrCompute('test', { q: 'a' }, compute)

    expect(r.hit).toBe(false)
    expect(compute).toHaveBeenCalledTimes(2)
  })

  it('embedding 路径：extractor 拼出来的字符串送入 embedder', async () => {
    const seenTexts: string[] = []
    const trackEmbedder = async (text: string) => {
      seenTexts.push(text)
      return [1, 0, 0, 0]
    }
    const cache = new ToolCache({
      test: {
        ttlMs: 60_000, maxSize: 10,
        embeddingKey: {
          extractor: (a) => `${a.city}|${a.category}|${a.query}`,
          threshold: 0.85,
          embedder: trackEmbedder,
        },
      },
    })

    await cache.getOrCompute('test', { city: '成都', category: 'food', query: '美食' }, async () => 'r')
    await cache.getOrCompute('test', { city: '北京', category: 'food', query: '美食' }, async () => 'r')

    expect(seenTexts).toEqual(['成都|food|美食', '北京|food|美食'])
  })
})
