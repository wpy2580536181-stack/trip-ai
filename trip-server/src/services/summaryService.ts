import prisma from '../config/database'
import { createLLM } from '../config/llm'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'

const SLIDING_WINDOW = 10
const COMPRESS_THRESHOLD = SLIDING_WINDOW * 2
const MAX_RETRIES = 2
const RETRY_BASE_MS = 1000

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function commitSummary(conversationId: number, summary: string, previousSummary: string | null) {
  await prisma.conversation.update({
    where: { id: conversationId },
    data: { summary, summaryError: false, summaryAt: new Date() },
  })
  console.log(`[Summary] 对话 ${conversationId} 摘要${previousSummary ? '已追加更新' : '已生成'} (${summary.length} 字)`)
}

async function markSummaryFailed(conversationId: number) {
  await prisma.conversation.update({
    where: { id: conversationId },
    data: { summaryError: true },
  })
}

export async function compressConversation(conversationId: number): Promise<void> {
  try {
    const totalCount = await prisma.message.count({ where: { conversationId } })
    if (totalCount <= COMPRESS_THRESHOLD) return

    const conversation = await prisma.conversation.findUnique({
      where: { id: conversationId },
      select: { summary: true },
    })
    const previousSummary = conversation?.summary ?? null

    const oldCount = totalCount - COMPRESS_THRESHOLD
    const oldMessages = await prisma.message.findMany({
      where: { conversationId },
      orderBy: { createdAt: 'asc' },
      take: oldCount,
    })
    if (oldMessages.length === 0) return

    const dialogText = oldMessages
      .map(m => `${m.role === 'user' ? '用户' : '助手'}: ${m.content}`)
      .join('\n')

    let prompt: string
    let systemMsg: string

    if (previousSummary) {
      systemMsg = '你是一个对话摘要追加助手。请将新对话内容追加到已有摘要中，合并成一份完整的摘要。保留：目的地、预算、偏好、行程安排、已做出的决定。只输出摘要文本，不要加任何前缀。'
      prompt = `已有摘要：\n${previousSummary}\n\n新对话：\n${dialogText}\n\n请将新对话的关键信息合并到已有摘要中，输出完整摘要。`
    } else {
      systemMsg = '你是一个对话摘要助手。请用 2-3 句话概括以下对话，保留关键信息：目的地、预算、偏好、行程安排、已做出的决定。只输出摘要文本，不要加任何前缀。'
      prompt = `请概括以下对话：\n${dialogText}`
    }

    let summary: string | null = null
    let lastError: unknown

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const llm = createLLM({ streaming: false, temperature: 0.3 })
        const response = await llm.invoke([
          new SystemMessage(systemMsg),
          new HumanMessage(prompt),
        ])
        summary = (response.content as string).trim()
        if (summary) break
      } catch (e) {
        lastError = e
        console.warn(`[Summary] 第 ${attempt + 1} 次压缩失败:`, e instanceof Error ? e.message : e)
        if (attempt < MAX_RETRIES) {
          await sleep(RETRY_BASE_MS * (attempt + 1))
        }
      }
    }

    if (summary) {
      await commitSummary(conversationId, summary, previousSummary)
    } else {
      console.error(`[Summary] ${MAX_RETRIES + 1} 次重试全部失败，标记 summary_error`)
      await markSummaryFailed(conversationId)
    }
  } catch (e) {
    console.error('[Summary] 压缩流程异常:', e instanceof Error ? e.message : e)
    await markSummaryFailed(conversationId).catch(() => {})
  }
}
