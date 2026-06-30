#!/usr/bin/env ts-node
/**
 * 多轮 chat cache hit rate 演化测试
 *
 * 流程：
 * 1. 登录拿 token
 * 2. 发 turn 1（无 conversationId），记录 hitRate
 * 3. 发 turn 2（带 conversationId），记录 hitRate
 * 4. 发 turn 3（带 conversationId），记录 hitRate
 *
 * 用法：
 *   EVAL_BASE_URL=http://127.0.0.1:3000 npx ts-node eval/multi-turn-smoke.ts
 *
 * 输出：每轮的 prompt / cached / hitRate，3 个城市各跑一次
 */

const BASE = process.env.EVAL_BASE_URL || 'http://127.0.0.1:3000'
const USER = process.env.EVAL_USERNAME
const PASS = process.env.EVAL_PASSWORD

interface SSEEvent { type: string; content?: string; error?: string; data?: any; usage?: any }

interface TurnResult {
  index: number
  message: string
  prompt: number
  cached: number
  hitRate: number
  durationMs: number
  error?: string
}

async function login(): Promise<string> {
  const res = await fetch(`${BASE}/api/user/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  })
  if (!res.ok) throw new Error(`login failed: ${res.status} ${await res.text()}`)
  const data = (await res.json()) as { data?: { token?: string } }
  if (!data.data?.token) throw new Error(`no token in response`)
  return data.data.token
}

async function chatOnce(token: string, message: string, conversationId?: number): Promise<{ usage?: any; conversationId?: number; error?: string; text: string }> {
  const res = await fetch(`${BASE}/api/trip/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message, conversationId }),
  })
  if (!res.ok || !res.body) {
    return { error: `chat failed: ${res.status}`, text: '' }
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let text = ''
  let usage: any
  let returnedConvId: number | undefined
  let error: string | undefined

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const dataLines: string[] = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length === 0) continue
      const dataStr = dataLines.join('\n')
      try {
        const ev = JSON.parse(dataStr) as SSEEvent
        if (ev.type === 'chunk' && ev.content) text += ev.content
        if (ev.type === 'complete') {
          if (ev.data?.conversationId) returnedConvId = ev.data.conversationId
          if ((ev as any).usage) usage = (ev as any).usage
          else if (ev.data?.usage) usage = ev.data.usage
        }
        if (ev.type === 'error') error = ev.error || 'unknown'
      } catch {}
    }
  }
  return { usage, conversationId: returnedConvId, error, text }
}

interface Scenario {
  name: string
  turns: string[]
}

const SCENARIOS: Scenario[] = [
  {
    name: 'chengdu-3days',
    turns: [
      '帮我规划成都3日行程，带父母，慢节奏，喜欢美食和茶馆',
      '第二天能加个火锅吗，父母不太能吃辣',
      '那预算大概多少？三个人',
    ],
  },
  {
    name: 'tokyo-5days',
    turns: [
      '帮我规划东京5日行程，学生党，预算 8000 块',
      '推荐几个免费景点',
      '从机场到新宿怎么走最便宜',
    ],
  },
  {
    name: 'xian-2days-kid',
    turns: [
      '帮我规划西安2日行程，带 6 岁小孩，想看兵马俑但是怕他累',
      '第二天安排轻松点，最好有午休时间',
      '兵马俑附近有适合小孩吃的地方吗',
    ],
  },
]

async function runScenario(token: string, s: Scenario): Promise<TurnResult[]> {
  const results: TurnResult[] = []
  let conversationId: number | undefined

  for (let i = 0; i < s.turns.length; i++) {
    const message = s.turns[i]
    const start = Date.now()
    const r = await chatOnce(token, message, conversationId)
    const durationMs = Date.now() - start

    if (r.error) {
      results.push({ index: i + 1, message, prompt: 0, cached: 0, hitRate: 0, durationMs, error: r.error })
      break
    }

    if (r.conversationId) conversationId = r.conversationId

    const prompt = r.usage?.prompt ?? 0
    const cached = r.usage?.cached ?? 0
    const hitRate = prompt > 0 ? cached / prompt : 0
    results.push({ index: i + 1, message, prompt, cached, hitRate, durationMs })
  }

  return results
}

async function main() {
  console.log(`Multi-turn smoke test → ${BASE}\n`)
  const token = await login()
  console.log(`logged in.\n`)

  const allResults: Record<string, TurnResult[]> = {}
  for (const s of SCENARIOS) {
    console.log(`━━━ ${s.name} ━━━`)
    const results = await runScenario(token, s)
    allResults[s.name] = results
    for (const r of results) {
      const hitPct = (r.hitRate * 100).toFixed(1)
      const color = r.hitRate >= 0.5 ? '🟢' : r.hitRate >= 0.3 ? '🟡' : '🔴'
      if (r.error) {
        console.log(`  turn ${r.index}  ❌ ${r.error}  (${r.durationMs}ms)`)
      } else {
        console.log(`  turn ${r.index}  ${color} hitRate=${hitPct}%  prompt=${r.prompt.toLocaleString()}  cached=${r.cached.toLocaleString()}  (${r.durationMs}ms)`)
      }
    }
    console.log()
  }

  // 汇总
  console.log(`━━━ summary ━━━`)
  console.log(`scenario        | turn1    | turn2    | turn3    | avg`)
  for (const [name, rs] of Object.entries(allResults)) {
    const r1 = rs[0] ? `${(rs[0].hitRate * 100).toFixed(1)}%` : 'n/a'
    const r2 = rs[1] ? `${(rs[1].hitRate * 100).toFixed(1)}%` : 'n/a'
    const r3 = rs[2] ? `${(rs[2].hitRate * 100).toFixed(1)}%` : 'n/a'
    const valid = rs.filter(r => !r.error)
    const avg = valid.length > 0 ? (valid.reduce((s, r) => s + r.hitRate, 0) / valid.length * 100).toFixed(1) + '%' : 'n/a'
    console.log(`${name.padEnd(15)} | ${r1.padEnd(8)} | ${r2.padEnd(8)} | ${r3.padEnd(8)} | ${avg}`)
  }
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
