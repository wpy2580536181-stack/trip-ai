export const UNSPLASH_CONFIG = {
  accessKey: process.env.UNSPLASH_ACCESS_KEY || '',
  enabled: !!process.env.UNSPLASH_ACCESS_KEY,
  rateLimit: { maxPerHour: 50 },
  cacheTtlMs: 30 * 24 * 60 * 60 * 1000,
  concurrency: 10,
  searchTimeoutMs: 5000,
}
