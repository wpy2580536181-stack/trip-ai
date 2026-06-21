#!/usr/bin/env ts-node
/**
 * Eval 入口
 *
 * 用法：
 *   npm run eval                         # mock 模式
 *   npm run eval:real                    # 真实 agent（需启动后端 + eval-test 账号）
 *   npm run eval:real -- --id 001        # 跑指定
 *   npm run eval:real -- --tag multi-turn # 跑指定 tag
 *   npm run eval:cleanup                 # 清理 eval-test 账号所有数据
 *
 * 真实模式环境变量：
 *   EVAL_BASE_URL    默认 http://127.0.0.1:3000
 *   EVAL_USERNAME    默认 eval-test
 *   EVAL_PASSWORD    默认 EvalTest@2026
 *   EVAL_TIMEOUT_MS  默认 90000
 *
 * 退出码：
 *   0 = 全部通过
 *   1 = 有失败
 *   2 = runner 自身错误
 */

import { join } from 'node:path'
import chalk from 'chalk'

import { loadFixtures, runAll, runFixture, summarize } from './runner'
import { listEvaluators } from './registry'
import { RealAgent } from './real-agent'
import type { AgentOutput, Fixture } from './types'

const FIXTURES_DIR = join(__dirname, 'fixtures', 'trip-planning')

function parseArgs(): { ids: string[]; tags: string[]; realMode: boolean } {
  const args = process.argv.slice(2)
  const ids: string[] = []
  const tags: string[] = []
  let realMode = false

  for (let i = 0; i < args.length; i++) {
    const a = args[i]
    if (a === '--real') {
      realMode = true
    } else if (a === '--id' && args[i + 1]) {
      ids.push(args[++i])
    } else if (a === '--tag' && args[i + 1]) {
      tags.push(args[++i])
    } else if (a === '--help' || a === '-h') {
      printHelp()
      process.exit(0)
    }
  }
  return { ids, tags, realMode }
}

function printHelp() {
  console.log(`
Usage: npm run eval [options]

Options:
  --real               Run against real agent (requires backend running)
  --id <fixture-id>    Run a specific fixture
  --tag <tag>          Run fixtures with specific tag (can repeat)
  -h, --help           Show this help
`)
}

function filterFixtures(fixtures: Fixture[], ids: string[], tags: string[]): Fixture[] {
  return fixtures.filter((f) => {
    if (ids.length > 0 && !ids.includes(f.id)) return false
    if (tags.length > 0 && !tags.some((t) => f.tags?.includes(t))) return false
    return true
  })
}

async function main() {
  const { ids, tags, realMode } = parseArgs()

  console.log(chalk.bold.cyan('\n=== Trip Agent Eval ===\n'))
  console.log(chalk.gray(`fixtures: ${FIXTURES_DIR}`))
  console.log(chalk.gray(`mode: ${realMode ? 'REAL agent' : 'MOCK agent'}`))
  console.log(chalk.gray(`registered evaluators: ${listEvaluators().length} (${listEvaluators().join(', ')})\n`))

  let fixtures: Fixture[]
  try {
    fixtures = loadFixtures(FIXTURES_DIR)
  } catch (e) {
    console.error(chalk.red('加载 fixture 失败:'), e)
    process.exit(2)
  }

  const filtered = filterFixtures(fixtures, ids, tags)
  if (filtered.length === 0) {
    console.error(chalk.yellow('没有匹配的 fixture'))
    process.exit(2)
  }
  console.log(chalk.gray(`将跑 ${filtered.length}/${fixtures.length} 个 fixture\n`))

  // 跑
  const debug = process.env.EVAL_DEBUG === '1'
  const realAgent = realMode ? buildRealAgent() : null
  const results = await runAll(filtered, {
    mockAgent: realMode ? undefined : buildMockAgent(),
    agentFn: realMode && realAgent ? (f) => realAgent.run(f) : undefined,
    onAfterFixture: realAgent ? () => realAgent.delay() : undefined,
  })

  // Debug 模式：打印原始 agent 输出
  if (debug) {
    console.log(chalk.bold('\n=== DEBUG: 原始 Agent 输出 ===\n'))
    for (const r of results) {
      console.log(chalk.bold(`[${r.fixtureId}]`))
      if (r.agentOutput?.text) {
        console.log(chalk.gray('--- text 前 500 字 ---'))
        console.log(r.agentOutput.text.slice(0, 500))
        console.log(chalk.gray('--- text 后 500 字 ---'))
        console.log(r.agentOutput.text.slice(-500))
      }
      if (r.agentOutput?.json) {
        console.log(chalk.gray('--- json ---'))
        console.log(JSON.stringify(r.agentOutput.json, null, 2).slice(0, 800))
      }
      if (r.agentOutput?.toolCalls) {
        console.log(chalk.gray('--- toolCalls ---'))
        console.log(JSON.stringify(r.agentOutput.toolCalls, null, 2))
      }
      if (r.agentOutput?.error) {
        console.log(chalk.red('--- error ---'))
        console.log(r.agentOutput.error)
      }
      console.log()
    }
  }

  // 汇总
  const summary = summarize(results)

  // 打印详细结果
  console.log(chalk.bold('\n=== 详细结果 ===\n'))
  for (const r of results) {
    const status = r.pass ? chalk.green('✓ PASS') : chalk.red('✗ FAIL')
    console.log(`${status}  ${chalk.bold(r.fixtureId)}  ${chalk.gray(r.description)}`)
    if (r.error) {
      console.log(`        ${chalk.red('fixture 错误: ' + r.error)}`)
    }
    for (const [name, ev] of Object.entries(r.evaluatorResults)) {
      const sym = ev.pass ? chalk.green('  ✓') : chalk.red('  ✗')
      console.log(`        ${sym} ${chalk.gray(name)}${ev.reason ? chalk.red(' — ' + ev.reason) : ''}`)
    }
  }

  // 打印汇总
  console.log(chalk.bold('\n=== 汇总 ===\n'))
  const pct = (summary.passRate * 100).toFixed(1)
  const totalColor =
    summary.passRate === 1 ? chalk.green : summary.passRate >= 0.8 ? chalk.yellow : chalk.red
  console.log(
    `${totalColor(`${summary.passedFixtures}/${summary.totalFixtures} 通过`)} (${pct}%)  ${chalk.gray(`${summary.totalDurationMs}ms`)}`,
  )

  if (Object.keys(summary.byTag).length > 0) {
    console.log(chalk.bold('\n按 tag:'))
    for (const [tag, s] of Object.entries(summary.byTag)) {
      const t = `${s.passed}/${s.total}`
      const c = s.passRate === 1 ? chalk.green : s.passRate >= 0.8 ? chalk.yellow : chalk.red
      console.log(`  ${c(t.padEnd(7))}  ${tag}`)
    }
  }

  if (Object.keys(summary.byEvaluator).length > 0) {
    console.log(chalk.bold('\n按 evaluator:'))
    for (const [name, s] of Object.entries(summary.byEvaluator)) {
      const t = `${s.passed}/${s.total}`
      const c = s.passRate === 1 ? chalk.green : s.passRate >= 0.8 ? chalk.yellow : chalk.red
      console.log(`  ${c(t.padEnd(7))}  ${name}`)
    }
  }

  console.log()
  process.exit(summary.failedFixtures === 0 ? 0 : 1)
}

/* ============================================================
 * Mock Agent（用于本地测试 evaluator 不调真实 LLM）
 *
 * 注意：mock 仅用于"evaluator 实现自测"。
 * 生产 eval 必须用 --real 跑真实 agent。
 * ============================================================ */

function buildMockAgent() {
  return (fixture: import('./types').Fixture): import('./types').AgentOutput => {
    // 简单的 mock：根据 fixture.tags 分类返回
    const tags = fixture.tags || []
    const message = fixture.input.message

    // 反例 fixture
    if (tags.includes('rejection') || tags.includes('off-topic')) {
      return {
        text: '推荐这几个目的地：青岛、桂林、丽江，都是 6 月适合的。',
        json: undefined,
        toolCalls: [{ name: 'retrieve_knowledge' }],
      }
    }

    // 雨天 fixture
    if (tags.includes('weather-adaptation')) {
      return {
        text: '雨天推荐浙江省博物馆、灵隐寺，备选室内方案。',
        json: undefined,
        toolCalls: [{ name: 'getWeather' }, { name: 'retrieve_knowledge' }],
      }
    }

    // 行程 fixture
    if (fixture.expected.days && fixture.expected.days > 0) {
      const city = extractCityFromMessage(message) || '成都'
      const pois = (fixture.expected.must_contain_pois || []).map((p) => p.name || p.name_contains).filter(Boolean) as string[]
      const json = {
        city,
        days: fixture.expected.days,
        totalBudget: 3000,
        dailyItinerary: Array.from({ length: fixture.expected.days }, (_, i) => ({
          day: i + 1,
          morning: { spot: pois[i * 3] || `${city}景点${i * 3 + 1}` },
          afternoon: { spot: pois[i * 3 + 1] || `${city}景点${i * 3 + 2}` },
          evening: { spot: pois[i * 3 + 2] || `${city}美食${i * 3 + 3}`, ticket: '￥100' },
        })),
        budgetBreakdown: { accommodation: 1000, food: 800, transportation: 500, tickets: 500, other: 200 },
        tips: ['多喝水', '注意防晒'],
      }
      const textPois = pois.join('、')
      const keywords = (fixture.expected.must_contain_keywords || []).join('、')
      return {
        text: `${city} ${fixture.expected.days} 天行程：${textPois}。${keywords}`,
        json,
        toolCalls: [{ name: 'retrieve_knowledge' }, { name: 'retrieve_knowledge' }],
      }
    }

    return {
      text: '这是 mock 响应。',
      json: undefined,
      toolCalls: [],
    }
  }
}

function extractCityFromMessage(message: string): string | null {
  const cities = ['北京', '上海', '广州', '深圳', '成都', '重庆', '杭州', '西安', '南京', '苏州', '东京', '巴黎']
  for (const c of cities) {
    if (message.includes(c)) return c
  }
  return null
}

function buildRealAgent(): RealAgent {
  const baseUrl = process.env.EVAL_BASE_URL || 'http://127.0.0.1:3000'
  const username = process.env.EVAL_USERNAME || 'eval-test'
  const password = process.env.EVAL_PASSWORD || 'EvalTest@2026'
  const timeoutMs = Number(process.env.EVAL_TIMEOUT_MS) || 90000
  const delayBetweenMs = Number(process.env.EVAL_DELAY_MS) || 2000

  console.log(chalk.gray(`  baseUrl: ${baseUrl}`))
  console.log(chalk.gray(`  username: ${username}`))
  console.log(chalk.gray(`  timeoutMs: ${timeoutMs}`))
  console.log(chalk.gray(`  delayBetweenMs: ${delayBetweenMs}`))

  const agent = new RealAgent({ baseUrl, username, password, timeoutMs, delayBetweenMs })
  return agent
}

main().catch((e) => {
  console.error(chalk.red('runner 出错:'), e)
  process.exit(2)
})
