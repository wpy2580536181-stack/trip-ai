import prisma from '../config/database'
import { createLLM } from '../config/llm'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'
import { estimateTokens, getHistoryMaxTokens } from '../utils/tokens'

const MAX_RETRIES = 2
const RETRY_BASE_MS = 1000
const APPEND_MARKER = '### 追加于'

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function commitAppendSummary(conversationId: number, newChunk: string, previousSummary: string | null) {
  const merged = previousSummary
    ? `${previousSummary}\n\n${APPEND_MARKER} ${new Date().toISOString().slice(0, 10)}\n${newChunk}`
    : newChunk
  await prisma.conversation.update({
    where: { id: conversationId },
    data: { summary: merged, summaryError: false, summaryAt: new Date() },
  })
  console.log(`[Summary] 对话 ${conversationId} ${previousSummary ? '已追加摘要段' : '已生成摘要'} (${newChunk.length}字)`)
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

    const messages = await prisma.message.findMany({
      where: { conversationId },
      orderBy: { createdAt: 'asc' },
    })
    if (messages.length === 0) return

    // 从最新消息往前累计 token，找出超出预算的旧消息
    let tokenSum = 0
    let cutIdx = messages.length
    for (let i = messages.length - 1; i >= 0; i--) {
      tokenSum += estimateTokens(messages[i].content)
      if (tokenSum > maxTokens) {
        cutIdx = i + 1
        break
      }
    }
    if (cutIdx === messages.length) return

    const oldMessages = messages.slice(0, cutIdx)
    if (oldMessages.length === 0) return

    const conversation = await prisma.conversation.findUnique({
      where: { id: conversationId },
      select: { summary: true },
    })
    const previousSummary = conversation?.summary ?? null

    const dialogText = oldMessages
      .map(m => `${m.role === 'user' ? '用户' : '助手'}: ${m.content}`)
      .join('\n')

    // append 模式：只对新增的旧消息生成新段，LLM 不再看到旧摘要
    // 旧摘要完整保留在 DB（hash 不变），新段追加到末尾
    const systemMsg = '你是一个对话摘要助手。请分析以下对话，生成一段 100-200 字的摘要，重点记录关键决策（目的地/预算/偏好/行程安排）和新发现的方向。摘要会追加到已有摘要末尾，所以请只关注本次对话的新信息，不要重复已有内容。直接输出摘要文本，不要加任何前缀或标题。'
    const prompt = `对话：\n${dialogText}\n\n请生成 100-200 字的摘要：`

    let newChunk: string | null = null

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const llm = createLLM({ streaming: false, temperature: 0.3 })
        const response = await llm.invoke([
          new SystemMessage(systemMsg),
          new HumanMessage(prompt),
        ])
        const text = (response.content as string).trim()
        if (text && text.length >= 20) {
          newChunk = text
          break
        }
      } catch (e) {
        console.warn(`[Summary] 第 ${attempt + 1} 次压缩失败:`, e instanceof Error ? e.message : e)
        if (attempt < MAX_RETRIES) {
          await sleep(RETRY_BASE_MS * (attempt + 1))
        }
      }
    }

    if (newChunk) {
      await commitAppendSummary(conversationId, newChunk, previousSummary)
    } else {
      console.error(`[Summary] ${MAX_RETRIES + 1} 次重试全部失败，标记 summary_error`)
      await markSummaryFailed(conversationId)
    }
  } catch (e) {
    console.error('[Summary] 压缩流程异常:', e instanceof Error ? e.message : e)
    await markSummaryFailed(conversationId).catch(() => {})
  }
}
