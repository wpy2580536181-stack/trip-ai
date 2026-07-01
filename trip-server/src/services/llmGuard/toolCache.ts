import { type CacheAdapter, TTLCache } from './cache'
import { agentLog as log } from '../../utils/logger'
import { embedText } from '../../config/embeddings'

export interface EmbeddingKeyConfig {
  /** 从 args 提取用于 embedding 归一化的字符串（一般拼关键字段） */
  extractor: (args: Record<string, unknown>) => string
  /** 相似度阈值 0-1，超过视为命中（默认 0.85） */
  threshold?: number
  /** 可选：注入的 embedding 函数（默认用 bge-small-zh-v1.5）；单测时可注入 deterministic 实现 */
  embedder?: (text: string) => Promise<number[]>
}

export interface ToolCacheConfig {
  /** 该 tool 的缓存 TTL（毫秒） */
  ttlMs: number
  /** 该 tool 缓存最大条目数（超过按 LRU 淘汰） */
  maxSize: number
  /**
   * 可选：embedding 归一化配置。
   * 提供则走 embedding 相似度路径，否则走字面归一化路径。
   *
   * 适用场景：tool 的某个字段（通常是 query）字面多变但语义相似
   * 例如 retrieve_knowledge 的 query="成都美食" / "成都好吃的" / "成都必吃川菜"
   */
  embeddingKey?: EmbeddingKeyConfig
}

interface ToolEntry {
  value: string
  /** 字面 key（字面路径用）；embedding 路径下为 'embed:<text>' 占位 */
  literalKey: string
  /** embedding 向量（embedding 路径用）；字面路径为 null */
  vector: number[] | null
}

export type CacheFactory = (config: ToolCacheConfig, toolName: string) => CacheAdapter<ToolEntry>

/**
 * 按 tool 维度隔离的缓存管理器。
 *
 * 支持两种归一化路径（per-tool 独立）：
 * - 字面归一化（默认）：trim + lowercase + sort keys
 * - embedding 归一化：算 query embedding，遍历 cache 找 cosine sim ≥ threshold 的 entry
 *
 * Key 归一化（字面）：
 * - 排序 object keys（让 {a, b} = {b, a}）
 * - string 字段 trim + toLowerCase
 * - 数字 / boolean 保持原样
 * - 跳过 undefined / null 字段
 *
 * cacheFactory：可注入 RedisTTLCache 等后端，默认用 TTLCache（进程内内存）。
 */
export class ToolCache {
  private caches = new Map<string, CacheAdapter<ToolEntry>>()
  private configs: Map<string, ToolCacheConfig>

  constructor(
    configs: Record<string, ToolCacheConfig>,
    cacheFactory?: CacheFactory,
  ) {
    this.configs = new Map(Object.entries(configs))
    const defaultFactory: CacheFactory = (cfg) => {
      const inner = new TTLCache<ToolEntry>({ maxSize: cfg.maxSize, defaultTtlMs: cfg.ttlMs })
      return {
        get: (key) => inner.aget(key),
        set: (key, value, ttlMs) => inner.aset(key, value, ttlMs),
        values: () => inner.avalues(),
      }
    }
    const factory: CacheFactory = cacheFactory ?? defaultFactory
    for (const [toolName, cfg] of this.configs) {
      this.caches.set(toolName, factory(cfg, toolName))
    }
  }

  async getOrCompute(
    toolName: string,
    args: Record<string, unknown>,
    compute: () => Promise<string>,
  ): Promise<{ result: string; hit: boolean }> {
    const cfg = this.configs.get(toolName)
    const cache = this.caches.get(toolName)
    if (!cfg || !cache) {
      const result = await compute()
      return { result, hit: false }
    }

    // 路径 A：字面归一化
    if (!cfg.embeddingKey) {
      return this.literalLookup(toolName, args, compute, cache, cfg)
    }

    // 路径 B：embedding 归一化
    return this.embeddingLookup(toolName, args, compute, cache, cfg)
  }

  private async literalLookup(
    toolName: string,
    args: Record<string, unknown>,
    compute: () => Promise<string>,
    cache: CacheAdapter<ToolEntry>,
    cfg: ToolCacheConfig,
  ): Promise<{ result: string; hit: boolean }> {
    const literalKey = this.makeLiteralKey(toolName, args)
    const cached = await cache.get(literalKey)
    if (cached !== undefined) {
      log.info({ toolName, hit: true, mode: 'literal', key: literalKey }, 'tool cache hit')
      return { result: cached.value, hit: true }
    }

    const result = await compute()
    await cache.set(literalKey, { value: result, literalKey, vector: null }, cfg.ttlMs)
    log.info({ toolName, hit: false, mode: 'literal', key: literalKey, resultLen: result.length }, 'tool cache miss')
    return { result, hit: false }
  }

  private async embeddingLookup(
    toolName: string,
    args: Record<string, unknown>,
    compute: () => Promise<string>,
    cache: CacheAdapter<ToolEntry>,
    cfg: ToolCacheConfig,
  ): Promise<{ result: string; hit: boolean }> {
    const ek = cfg.embeddingKey!
    const threshold = ek.threshold ?? 0.85
    const embedder = ek.embedder ?? embedText
    const keyText = ek.extractor(args)
    const queryVec = await embedder(keyText)

    let bestSim = -1
    let bestEntry: ToolEntry | null = null
    for (const entry of await cache.values()) {
      if (!entry.vector) continue
      const sim = dotProduct(queryVec, entry.vector)
      if (sim > bestSim) {
        bestSim = sim
        bestEntry = entry
      }
    }

    if (bestEntry && bestSim >= threshold) {
      log.info(
        { toolName, hit: true, mode: 'embedding', sim: bestSim.toFixed(3), threshold, keyText },
        'tool cache hit',
      )
      return { result: bestEntry.value, hit: true }
    }

    const result = await compute()
    const entryKey = `embed:${keyText}`
    await cache.set(entryKey, { value: result, literalKey: entryKey, vector: queryVec }, cfg.ttlMs)
    log.info(
      {
        toolName,
        hit: false,
        mode: 'embedding',
        bestSim: bestSim < 0 ? 'none' : bestSim.toFixed(3),
        keyText,
        resultLen: result.length,
      },
      'tool cache miss',
    )
    return { result, hit: false }
  }

  private makeLiteralKey(toolName: string, args: Record<string, unknown>): string {
    const normalized = Object.keys(args)
      .sort()
      .reduce<Record<string, unknown>>((acc, k) => {
        const v = args[k]
        if (v === undefined || v === null) return acc
        acc[k] = typeof v === 'string' ? v.trim().toLowerCase() : v
        return acc
      }, {})
    return `${toolName}:${JSON.stringify(normalized)}`
  }
}

/**
 * 点积 = cosine 相似度（前提：两向量已 L2 normalize）。
 * bge-small-zh-v1.5 在 embedText 里用 normalize: true，输出已 unit length。
 */
function dotProduct(a: number[], b: number[]): number {
  let sum = 0
  const len = Math.min(a.length, b.length)
  for (let i = 0; i < len; i++) sum += a[i] * b[i]
  return sum
}
