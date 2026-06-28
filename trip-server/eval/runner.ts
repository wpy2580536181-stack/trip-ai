/**
 * Eval Runner
 * 加载 fixture → 调 Agent → 跑所有 evaluator → 收集结果
 *
 * 阶段：
 * 1) loadFixtures(): 解析所有 YAML
 * 2) runAgent(fixture): 调真实 Agent 拿 AgentOutput
 *    这里是 mock 实现，需要替换为实际 tripService 调用
 * 3) runFixture(fixture): 跑一个 fixture 的所有 evaluator
 * 4) runAll(): 跑全部 fixture + 生成报告
 */

import { readFileSync, readdirSync, statSync, type Dirent } from 'node:fs'
import { join } from 'node:path'
import yaml from 'js-yaml'

import type {
  AgentOutput,
  EvalResult,
  Fixture,
  FixtureResult,
  ReportSummary,
} from './types'

export type { FixtureResult, ReportSummary }
import { getEvaluator } from './registry'

const log = {
  info: (msg: string, extra?: any) => console.log(`[eval] ${msg}`, extra ?? ''),
  warn: (msg: string, extra?: any) => console.warn(`[eval] ${msg}`, extra ?? ''),
  error: (msg: string, extra?: any) => console.error(`[eval] ${msg}`, extra ?? ''),
}

/* ============================================================
 * 1. Fixture 加载
 * ============================================================ */

/** 递归扫 fixturesDir 下所有 .yaml/.yml 文件（跳过 .gitkeep） */
function findFixtureFiles(fixturesDir: string): string[] {
  const out: string[] = []
  let entries: Dirent<string>[]
  try {
    entries = readdirSync(fixturesDir, { withFileTypes: true }) as Dirent<string>[]
  } catch (e) {
    log.error(`读取 fixtures 目录失败: ${fixturesDir}`, e)
    return out
  }
  for (const e of entries) {
    const full = join(fixturesDir, e.name)
    if (e.isDirectory()) {
      out.push(...findFixtureFiles(full))
    } else if ((e.name.endsWith('.yaml') || e.name.endsWith('.yml')) && e.name !== '.gitkeep') {
      out.push(full)
    }
  }
  return out
}

export function loadFixtures(fixturesDir: string): Fixture[] {
  const files = findFixtureFiles(fixturesDir)
  const fixtures: Fixture[] = []

  for (const fullPath of files) {
    const file = fullPath.slice(fixturesDir.length + 1)
    try {
      const content = readFileSync(fullPath, 'utf-8')
      const parsed = yaml.load(content) as Fixture
      if (!parsed.id || !parsed.input || !parsed.expected) {
        log.warn(`fixture ${file} 缺少必要字段（id/input/expected），跳过`)
        continue
      }
      fixtures.push(parsed)
    } catch (e) {
      log.error(`fixture ${file} 解析失败:`, e)
    }
  }

  log.info(`加载了 ${fixtures.length} 个 fixture`)
  return fixtures
}

/* ============================================================
 * 2. 跑单个 fixture
 * ============================================================ */

export interface RunFixtureOptions {
  /** mock agent：测试 evaluator 时用，不调真实 LLM */
  mockAgent?: (fixture: Fixture) => AgentOutput
  /** 真实 agent：生产 eval 用 */
  agentFn?: (fixture: Fixture) => Promise<AgentOutput>
  /** fixture 完成后调用（用来加间隔） */
  onAfterFixture?: (fixture: Fixture) => Promise<void> | void
  /** fixture 完成后回调（实时进度上报） */
  onProgress?: (result: FixtureResult) => void
  /**
   * 多采样：跑 N 次取多数
   * mock 模式无效（每次结果相同）
   * 真实模式：能降低 LLM 波动，但耗 token ×N
   * 默认 1（单次），建议真实模式用 3
   */
  samples?: number
}

export async function runFixture(
  fixture: Fixture,
  options: RunFixtureOptions = {},
): Promise<FixtureResult> {
  const start = Date.now()
  const samples = Math.max(1, options.samples ?? 1)
  const evaluatorResults: Record<string, EvalResult> = {}
  const allOutputs: AgentOutput[] = []
  let lastError: string | undefined

  // 1) 拿 Agent 输出（多采样）
  for (let s = 0; s < samples; s++) {
    let output: AgentOutput | undefined
    let error: string | undefined

    try {
      if (options.agentFn) {
        output = await options.agentFn(fixture)
      } else if (options.mockAgent) {
        output = options.mockAgent(fixture)
      } else {
        throw new Error('必须提供 mockAgent 或 agentFn')
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      log.error(`fixture ${fixture.id} 第 ${s + 1} 次 Agent 调用失败: ${error}`)
    }

    if (output) allOutputs.push(output)
    if (error) lastError = error

    // 1.5) fixture 完成后钩子（RealAgent 用它做间隔）
    if (options.onAfterFixture) {
      try {
        await options.onAfterFixture(fixture)
      } catch (e) {
        log.warn(`onAfterFixture 钩子失败: ${e instanceof Error ? e.message : e}`)
      }
    }

    if (samples > 1) log.info(`  [${fixture.id}] sample ${s + 1}/${samples} 完成`)
  }

  const output = allOutputs[0]  // 主输出（用于 report）
  const error = lastError

  // 多采样：每个 evaluator 跑 N 次，**多数**决定 pass/fail
  if (samples > 1 && allOutputs.length > 0) {
    for (const name of fixture.evaluators) {
      const evaluator = getEvaluator(name)
      if (!evaluator) {
        evaluatorResults[name] = { pass: false, reason: `evaluator "${name}" 未注册` }
        continue
      }
      const perSample: EvalResult[] = []
      for (const o of allOutputs) {
        try {
          perSample.push(evaluator(o, fixture))
        } catch (e) {
          perSample.push({
            pass: false,
            reason: `evaluator "${name}" 抛错: ${e instanceof Error ? e.message : String(e)}`,
          })
        }
      }
      const passCount = perSample.filter((r) => r.pass).length
      const majority = passCount > perSample.length / 2
      evaluatorResults[name] = {
        pass: majority,
        reason: majority
          ? undefined
          : perSample.find((r) => !r.pass)?.reason || `${passCount}/${perSample.length} 样本失败`,
        details: { passCount, totalSamples: perSample.length, perSample },
      }
    }
  } else {
    // 2) 跑每个 evaluator（单采样）
    if (output) {
      for (const name of fixture.evaluators) {
        const evaluator = getEvaluator(name)
        if (!evaluator) {
          evaluatorResults[name] = {
            pass: false,
            reason: `evaluator "${name}" 未注册`,
          }
          continue
        }
        try {
          evaluatorResults[name] = evaluator(output, fixture)
        } catch (e) {
          evaluatorResults[name] = {
            pass: false,
            reason: `evaluator "${name}" 抛错: ${e instanceof Error ? e.message : String(e)}`,
          }
        }
      }
    }
  }

  // 3) 整体 pass = 所有 evaluator 都 pass
  const pass = Object.values(evaluatorResults).every((r) => r.pass)

  return {
    fixtureId: fixture.id,
    description: fixture.description,
    tags: fixture.tags || [],
    agentOutput: output,
    evaluatorResults,
    pass,
    durationMs: Date.now() - start,
    error,
  }
}

/* ============================================================
 * 3. 跑全部 fixture
 * ============================================================ */

export async function runAll(
  fixtures: Fixture[],
  options: RunFixtureOptions = {},
): Promise<FixtureResult[]> {
  const results: FixtureResult[] = []
  for (const f of fixtures) {
    log.info(`[${f.id}] ${f.description}`)
    const r = await runFixture(f, options)
    results.push(r)
    const status = r.pass ? '✓' : '✗'
    const failed = Object.entries(r.evaluatorResults)
      .filter(([, v]) => !v.pass)
      .map(([k, v]) => `${k}: ${v.reason}`)
      .join(' | ')
    log.info(`  ${status} ${r.durationMs}ms${failed ? ` 失败: ${failed}` : ''}`)
    if (options.onProgress) options.onProgress(r)
  }
  return results
}

/* ============================================================
 * 4. 报告汇总
 * ============================================================ */

export function summarize(results: FixtureResult[]): ReportSummary {
  const total = results.length
  const passed = results.filter((r) => r.pass).length
  const totalDuration = results.reduce((s, r) => s + r.durationMs, 0)

  // Token 累计（取主输出的 tokens）
  let totalTokens: ReportSummary['totalTokens']
  let hasTokens = false
  const tokensAgg = { prompt: 0, completion: 0, total: 0, cached: 0 }
  for (const r of results) {
    if (r.agentOutput?.tokens) {
      tokensAgg.prompt += r.agentOutput.tokens.prompt
      tokensAgg.completion += r.agentOutput.tokens.completion
      tokensAgg.total += r.agentOutput.tokens.total
      tokensAgg.cached += r.agentOutput.tokens.cached ?? 0
      hasTokens = true
    }
  }
  if (hasTokens) {
    const hitRate = tokensAgg.prompt > 0 ? tokensAgg.cached / tokensAgg.prompt : 0
    totalTokens = { ...tokensAgg, hitRate }
  }

  // 按 tag
  const byTag: ReportSummary['byTag'] = {}
  for (const r of results) {
    for (const tag of r.tags.length ? r.tags : ['(untagged)']) {
      if (!byTag[tag]) byTag[tag] = { total: 0, passed: 0, passRate: 0 }
      byTag[tag].total += 1
      if (r.pass) byTag[tag].passed += 1
    }
  }
  for (const tag of Object.keys(byTag)) {
    byTag[tag].passRate = byTag[tag].total ? byTag[tag].passed / byTag[tag].total : 0
  }

  // 按 evaluator
  const byEvaluator: ReportSummary['byEvaluator'] = {}
  for (const r of results) {
    for (const [name, evalResult] of Object.entries(r.evaluatorResults)) {
      if (!byEvaluator[name]) byEvaluator[name] = { total: 0, passed: 0, passRate: 0 }
      byEvaluator[name].total += 1
      if (evalResult.pass) byEvaluator[name].passed += 1
    }
  }
  for (const name of Object.keys(byEvaluator)) {
    byEvaluator[name].passRate = byEvaluator[name].total ? byEvaluator[name].passed / byEvaluator[name].total : 0
  }

  return {
    totalFixtures: total,
    passedFixtures: passed,
    failedFixtures: total - passed,
    passRate: total ? passed / total : 0,
    totalDurationMs: totalDuration,
    byTag,
    byEvaluator,
    totalTokens,
  }
}
