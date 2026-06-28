export const AMAP_CONFIG = {
  apiKey: process.env.AMAP_MAPS_API_KEY || '',
  enabled: !!process.env.AMAP_MAPS_API_KEY,
  rateLimit: {
    maxPerSecond: 3,
    maxPerHour: 100,
  },
  circuitBreaker: {
    maxFailures: 10,
    resetTimeoutMs: 10 * 60 * 1000,
  },
  cacheTtlMs: 30 * 60 * 1000,
  process: {
    healthCheckIntervalMs: 30 * 1000,
    restartBackoffMs: 1000,
    restartMaxBackoffMs: 16_000,
    restartMaxPerMinute: 3,
    timeoutMs: 10_000,
  },
}
