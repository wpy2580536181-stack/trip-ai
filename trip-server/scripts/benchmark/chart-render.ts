/**
 * 图表生成
 *
 * 从 trip-server/docs/performance-data/*.json 生成 6 张 PNG
 * 用 chartjs-node-canvas
 */

import { ChartJSNodeCanvas } from 'chartjs-node-canvas'
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs'
import { join } from 'path'
import { percentile } from './lib/result-store'

const DATA_DIR = join(__dirname, '..', '..', 'docs', 'performance-data')
const CHARTS_DIR = join(DATA_DIR, 'charts')
const WIDTH = 800
const HEIGHT = 400

function ensureDir() {
  if (!existsSync(CHARTS_DIR)) mkdirSync(CHARTS_DIR, { recursive: true })
}

function loadJson(name: string): any {
  return JSON.parse(readFileSync(join(DATA_DIR, `${name}.json`), 'utf8'))
}

async function renderChart(config: any): Promise<Buffer> {
  const chart = new ChartJSNodeCanvas({ width: WIDTH, height: HEIGHT, backgroundColour: 'white' })
  return chart.renderToBuffer(config)
}

function saveChart(name: string, buf: Buffer) {
  const path = join(CHARTS_DIR, `${name}.png`)
  writeFileSync(path, buf)
  console.log(`[chart] ${path}`)
}

async function main() {
  ensureDir()

  // 1. QPS-P99 柱状图（普通 HTTP）
  const http = loadJson('http-results')
  const loginQps = http.login.effectiveQps ?? http.login.qps
  const historyQps = http.history.effectiveQps ?? http.history.qps
  await saveChart('qps-p99', await renderChart({
    type: 'bar',
    data: {
      labels: ['登录', '历史'],
      datasets: [
        { label: 'QPS (有效)', data: [loginQps, historyQps], yAxisID: 'y', backgroundColor: 'rgba(54, 162, 235, 0.6)' },
        { label: 'P99 (ms)', data: [http.login.p99, http.history.p99], yAxisID: 'y1', backgroundColor: 'rgba(255, 99, 132, 0.6)' },
      ],
    },
    options: {
      title: { display: true, text: '普通 HTTP 压测 (10 并发 / 30s)' },
      scales: {
        y: { type: 'linear', position: 'left', title: { display: true, text: 'QPS' } },
        y1: { type: 'linear', position: 'right', title: { display: true, text: 'P99 (ms)' }, grid: { drawOnChartArea: false } },
      },
    },
  }))

  // 2. SSE 并发 vs 延迟
  const sse = loadJson('sse-results')
  await saveChart('sse-concurrency', await renderChart({
    type: 'line',
    data: {
      labels: sse.results.map((r: any) => String(r.concurrency)),
      datasets: [
        { label: 'P50 (s)', data: sse.results.map((r: any) => Math.round(percentile(r.streamDurationsMs, 50) / 100) / 10), borderColor: 'rgb(75, 192, 192)', fill: false },
        { label: 'P95 (s)', data: sse.results.map((r: any) => Math.round(percentile(r.streamDurationsMs, 95) / 100) / 10), borderColor: 'rgb(255, 205, 86)', fill: false },
        { label: 'P99 (s)', data: sse.results.map((r: any) => Math.round(percentile(r.streamDurationsMs, 99) / 100) / 10), borderColor: 'rgb(255, 99, 132)', fill: false },
      ],
    },
    options: {
      title: { display: true, text: 'SSE 流式 vs 并发' },
      scales: { y: { title: { display: true, text: '流耗时 (秒)' } } },
    },
  }))

  // 3. LLM 耗时
  const llm = loadJson('llm-results')
  await saveChart('llm-tokens', await renderChart({
    type: 'bar',
    data: {
      labels: llm.results.map((r: any) => `${r.city} ${r.days}d`),
      datasets: [{ label: '耗时 (秒)', data: llm.results.map((r: any) => Math.round(r.durationMs / 100) / 10), backgroundColor: 'rgba(153, 102, 255, 0.6)' }],
    },
    options: { title: { display: true, text: 'LLM /recommend 耗时' }, scales: { y: { title: { display: true, text: '秒' } } } },
  }))

  // 4. 缓存命中率
  const cache = loadJson('cache-results')
  const cacheMiss = cache.totalTokens - cache.cachedTokens
  await saveChart('cache-hitrate', await renderChart({
    type: 'doughnut',
    data: {
      labels: ['Cache 命中', 'Cache 未命中'],
      datasets: [{ data: [cache.cachedTokens, cacheMiss], backgroundColor: ['rgba(75, 192, 192, 0.8)', 'rgba(255, 99, 132, 0.8)'] }],
    },
    options: { title: { display: true, text: `DeepSeek Prompt Cache 命中率: ${(cache.cacheHitRate * 100).toFixed(1)}%` } },
  }))

  // 5. 资源
  const env = loadJson('env')
  await saveChart('resources', await renderChart({
    type: 'bar',
    data: {
      labels: ['CPU 核数', '总内存 GB', '可用内存 GB'],
      datasets: [{ label: '机器资源', data: [env.cpus, Math.round(env.totalMemMB / 1024 * 10) / 10, Math.round(env.freeMemMB / 1024 * 10) / 10], backgroundColor: 'rgba(54, 162, 235, 0.6)' }],
    },
    options: { title: { display: true, text: '压测环境' } },
  }))

  // 6. P50/P95/P99 对比
  const sseRow = sse.results.find((r: any) => r.concurrency === 10)
  const sseP50 = sseRow ? percentile(sseRow.streamDurationsMs, 50) : 0
  const sseP95 = sseRow ? percentile(sseRow.streamDurationsMs, 95) : 0
  const sseP99 = sseRow ? percentile(sseRow.streamDurationsMs, 99) : 0
  await saveChart('p-percentiles', await renderChart({
    type: 'bar',
    data: {
      labels: ['登录', '历史', 'LLM /recommend', 'SSE chat (10 并发)'],
      datasets: [
        { label: 'P50', data: [http.login.p50, http.history.p50, llm.durationP50, sseP50], backgroundColor: 'rgba(75, 192, 192, 0.6)' },
        { label: 'P95', data: [http.login.p95, http.history.p95, llm.durationP95, sseP95], backgroundColor: 'rgba(255, 205, 86, 0.6)' },
        { label: 'P99', data: [http.login.p99, http.history.p99, llm.durationP99, sseP99], backgroundColor: 'rgba(255, 99, 132, 0.6)' },
      ],
    },
    options: { title: { display: true, text: 'P50/P95/P99 对比' }, scales: { y: { type: 'logarithmic' } } },
  }))

  console.log('[chart] 全部完成')
}

main().catch((e) => { console.error(e); process.exit(1) })
