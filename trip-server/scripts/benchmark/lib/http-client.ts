/**
 * 压测 HTTP 客户端
 *
 * 统一的 fetch 封装 + 计时 + 状态码记录
 */

export interface HttpMetric {
  url: string
  method: string
  status: number
  durationMs: number
  ok: boolean
  bytes: number
}

export async function timedFetch(
  url: string,
  opts: RequestInit = {},
): Promise<HttpMetric & { body: string }> {
  const start = Date.now()
  const res = await fetch(url, opts)
  const body = await res.text()
  return {
    url,
    method: opts.method || 'GET',
    status: res.status,
    durationMs: Date.now() - start,
    ok: res.ok,
    bytes: body.length,
    body,
  }
}

/** 并发跑 N 次，返回所有指标 */
export async function runConcurrent(
  url: string,
  opts: RequestInit,
  concurrency: number,
  totalRequests: number,
): Promise<HttpMetric[]> {
  const results: HttpMetric[] = []
  const queue: number[] = Array.from({ length: totalRequests }, (_, i) => i)
  async function worker() {
    while (queue.length > 0) {
      queue.shift()
      try {
        const r = await timedFetch(url, opts)
        results.push(r)
      } catch (e) {
        results.push({
          url, method: opts.method || 'GET',
          status: 0, durationMs: 0, ok: false, bytes: 0,
        })
      }
    }
  }
  await Promise.all(Array.from({ length: concurrency }, () => worker()))
  return results
}
