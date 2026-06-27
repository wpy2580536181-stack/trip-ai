import prisma from '../config/database'
import { createLLM } from '../config/llm'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'
import {
  estimateTokens,
  getHistoryMaxTokens,
  DEFAULT_COMPACTION_TARGET_TOKENS,
} from '../utils/tokens'
import { getContextMessages } from './conversationService'
import { summaryLog as log } from '../utils/logger'

const MAX_RETRIES = 2
const RETRY_BASE_MS = 1000
const APPEND_MARKER = '### 追加于'

interface LayeredSummary {
  summary: string | null
  recap: string | null
}

export interface CompactionSelection<T> {
  toCompact: T[]
  toKeep: T[]
  freedTokens: number
}

/**
 * 纯函数：根据 TAIL 当前总量和目标 token 数，从最老开始贪心选出要压缩的消息。
 * - 目标：把 TAIL 压到 targetTokens（留 buffer）
 * - 选法：从最老开始累加 token，凑够需要释放的量即停
 * - 边界：totalTokens ≤ targetTokens → 不压缩（返回 toCompact=[]）
 */
export function selectCompactionRange<T extends { content: string }>(
  messages: T[],
  totalTokens: number,
  targetTokens: number,
): CompactionSelection<T> {
  if (totalTokens <= targetTokens) {
    return { toCompact: [], toKeep: messages, freedTokens: 0 }
  }
  const tokensToFree = totalTokens - targetTokens
  let freed = 0
  let count = 0
  for (const msg of messages) {
    freed += estimateTokens(msg.content)
    count++
    if (freed >= tokensToFree) break
  }
  // 边界保护：单条消息就超过 target 时，至少压缩 1 条
  if (count === 0) count = 1
  return {
    toCompact: messages.slice(0, count),
    toKeep: messages.slice(count),
    freedTokens: freed,
  }
}

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function formatDateMarker(): string {
  return `${APPEND_MARKER} ${new Date().toISOString().slice(0, 10)}`
}

function appendChunk(previous: string | null, marker: string, chunk: string): string {
  return previous ? `${previous}\n\n${marker}\n${chunk}` : chunk
}

/**
 * 解析 LLM 输出的分层摘要。
 * 期望格式：
 *   ### 关键决策
 *   <summary 段>
 *   ### 对话脉络
 *   <recap 段>
 *
 * 兼容标题前多余空格、markdown 围栏等常见噪声；任一段缺失返回 null（不抛错）。
 */
export function parseLayeredSummary(raw: string): LayeredSummary {
  let text = raw.trim()
  // 去掉外层 ``` 代码块（容错）
  const fence = text.match(/^```[a-zA-Z]*\n([\s\S]*?)\n```\s*$/)
  if (fence) text = fence[1].trim()

  const summaryMatch = text.match(/###\s*关键决策\s*\n([\s\S]*?)(?=\n###\s*对话脉络|$)/)
  const recapMatch = text.match(/###\s*对话脉络\s*\n([\s\S]*?)$/)

  const summary = summaryMatch?.[1].trim() || null
  const recap = recapMatch?.[1].trim() || null

  return { summary, recap }
}

async function commitAppendLayered(
  conversationId: number,
  newSummaryChunk: string | null,
  newRecapChunk: string | null,
  previousSummary: string | null,
  previousRecap: string | null,
): Promise<{ wroteSummary: boolean; wroteRecap: boolean }> {
  const marker = formatDateMarker()
  const data: Record<string, unknown> = { summaryError: false, summaryAt: new Date() }

  if (newSummaryChunk) {
    data.summary = appendChunk(previousSummary, marker, newSummaryChunk)
  }
  if (newRecapChunk) {
    data.recap = appendChunk(previousRecap, marker, newRecapChunk)
  }

  await prisma.conversation.update({ where: { id: conversationId }, data })

  log.info(
    {
      conversationId,
      summaryLen: newSummaryChunk?.length ?? 0,
      recapLen: newRecapChunk?.length ?? 0,
      mode: previousSummary ? 'append' : 'new',
    },
    '分层摘要更新',
  )

  return { wroteSummary: !!newSummaryChunk, wroteRecap: !!newRecapChunk }
}

async function markSummaryFailed(conversationId: number) {
  await prisma.conversation.update({
    where: { id: conversationId },
    data: { summaryError: true },
  })
}

export async function compressConversation(conversationId: number): Promise<void> {
  try {
    const maxTokens = getHistoryMaxTokens()
    const ctx = await getContextMessages(conversationId, maxTokens)

    // 大多数轮次：TAIL 总量未超预算，跳过整个 LLM 调用
    if (!ctx.needsCompaction) return
    if (ctx.messages.length === 0) return

    // 目标：把 TAIL 压到 targetTokens（~12K），留 25% buffer 避免下一两轮又触发
    const targetTokens = DEFAULT_COMPACTION_TARGET_TOKENS
    const selection = selectCompactionRange(ctx.messages, ctx.totalTokens, targetTokens)
    if (selection.toCompact.length === 0) return
    const oldMessages = selection.toCompact

    const conversation = await prisma.conversation.findUnique({
      where: { id: conversationId },
      select: { summary: true, recap: true },
    })
    const previousSummary = conversation?.summary ?? null
    const previousRecap = conversation?.recap ?? null

    const dialogText = oldMessages
      .map(m => `${m.role === 'user' ? '用户' : '助手'}: ${m.content}`)
      .join('\n')

    // append 模式：旧摘要/脉络完整保留在 DB，新段 append 到字段末尾。
    // LLM 不再看到旧摘要，只对本次新增的旧消息生成新段，避免重复。
    const systemMsg = `你是一个对话摘要助手。请分析以下对话，按指定格式输出两层摘要。

## 输出格式（严格遵守）
必须输出两段，每段以 ### 开头的标题行作为锚点，标题与正文之间换行：

### 关键决策
<记录本次对话产生的关键决策：目的地、天数、预算、偏好、行程安排、住宿选择等已确定的事项，80-150 字>

### 对话脉络
<记录本次对话的脉络：讨论过的主题与方向、用户的兴趣演变、问过什么、还没问什么、关注点的变化，80-150 字>

## 追加规则
- 本次输出会追加到已有摘要/脉络的末尾，所以请只关注本次对话的新信息，不要重复已有内容
- 不要加 markdown 代码块、不要加任何前后缀解释文字，输出完直接结束`

    const prompt = `对话：\n${dialogText}\n\n请按格式输出关键决策和对话脉络两段：`

    let newSummaryChunk: string | null = null
    let newRecapChunk: string | null = null

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const llm = createLLM({ streaming: false, temperature: 0.3 })
        const response = await llm.invoke([
          new SystemMessage(systemMsg),
          new HumanMessage(prompt),
        ])
        const text = (response.content as string).trim()
        const parsed = parseLayeredSummary(text)
        // 至少拿到关键决策段才算成功；脉络段允许缺失（降级）
        if (parsed.summary && parsed.summary.length >= 20) {
          newSummaryChunk = parsed.summary
          newRecapChunk = parsed.recap && parsed.recap.length >= 20 ? parsed.recap : null
          break
        }
        log.warn(
          { attempt: attempt + 1, hasSummary: !!parsed.summary, hasRecap: !!parsed.recap },
          '解析未得到关键决策段',
        )
      } catch (e) {
        log.warn({ err: e, attempt: attempt + 1 }, '压缩失败')
      }
      if (attempt < MAX_RETRIES) {
        await sleep(RETRY_BASE_MS * (attempt + 1))
      }
    }

    if (newSummaryChunk) {
      await commitAppendLayered(
        conversationId,
        newSummaryChunk,
        newRecapChunk,
        previousSummary,
        previousRecap,
      )
      // 关键决策已写入但脉络缺失时，给运维一个轻量提示
      if (!newRecapChunk) {
        log.warn({ conversationId }, '本次仅写入 summary，recap 解析缺失或过短')
      }
      // 摘要成功写入后才物理标记这些消息为 excluded（failure-safe）
      // 失败时这批消息仍在 TAIL 中，下次 complete 事件会重试
      const oldIds = oldMessages.map(m => m.id)
      await prisma.message.updateMany({
        where: { id: { in: oldIds }, excludedFromContext: { not: true } },
        data: { excludedFromContext: true },
      })
      log.info(
        { conversationId, compacted: oldIds.length, freedTokens: selection.freedTokens },
        '旧消息标记为 excludedFromContext',
      )
    } else {
      log.error({ attempts: MAX_RETRIES + 1 }, '重试全部失败，标记 summary_error')
      await markSummaryFailed(conversationId)
    }
  } catch (e) {
    log.error({ err: e }, '压缩流程异常')
    await markSummaryFailed(conversationId).catch(() => {})
  }
}
