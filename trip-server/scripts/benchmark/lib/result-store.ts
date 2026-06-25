/**
 * 压测结果存储
 *
 * 统一写 docs/performance-data/*.json
 * 自动生成时间戳 + 环境快照
 */

import { writeFileSync, mkdirSync, existsSync } from 'fs'
import { join } from 'path'
import * as os from 'os'

const DATA_DIR = join(__dirname, '..', '..', '..', '..', 'docs', 'performance-data')

export interface BenchEnv {
  node: string
  platform: string
  arch: string
  cpus: number
  totalMemMB: number
  freeMemMB: number
  timestamp: string
}

export function getEnv(): BenchEnv {
  return {
    node: process.version,
    platform: process.platform,
    arch: process.arch,
    cpus: os.cpus().length,
    totalMemMB: Math.round(os.totalmem() / 1024 / 1024),
    freeMemMB: Math.round(os.freemem() / 1024 / 1024),
    timestamp: new Date().toISOString(),
  }
}

export function saveResult(name: string, data: any): void {
  if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true })
  const filePath = join(DATA_DIR, `${name}.json`)
  writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf8')
  console.log(`[save] ${filePath}`)
}

export function percentile(arr: number[], p: number): number {
  if (arr.length === 0) return 0
  const sorted = [...arr].sort((a, b) => a - b)
  const idx = Math.floor((sorted.length - 1) * (p / 100))
  return sorted[idx]
}
