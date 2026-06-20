import prisma from '../config/database'
import { createLLM } from '../config/llm'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'
import { estimateTokens, getHistoryMaxTokens } from '../utils/tokens'

const MAX_RETRIES = 2
const RETRY_BASE_MS = 1000

function sleep(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function commitSummary(conversationId: number, summary: string, recap: string, previousSummary: string | null) {
  await prisma.conversation.update({
    where: { id: conversationId },
    data: { summary, recap, summaryError: false, summaryAt: new Date() },
  })
  console.log(`[Summary] 对话 ${conversationId} 摘要${previousSummary ? '已追加更新' : '已生成'} (决策${summary.length}字, 脉络${recap.length}字)`)
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
    let cutIdx = messages.length  // 默认：全部消息都在预算内
    for (let i = messages.length - 1; i >= 0; i--) {
      tokenSum += estimateTokens(messages[i].content)
      if (tokenSum > maxTokens) {
        cutIdx = i + 1  // 索引 0 ~ i 是超出预算的旧消息
        break
      }
    }
    if (cutIdx === messages.length) return  // 全部消息都在预算内，无需压缩

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

    let prompt: string
    let systemMsg: string

    if (previousSummary) {
      systemMsg = '你是一个对话摘要助手。请分析新对话和已有摘要，输出更新后的两层摘要。严格按格式输出。'
      prompt = `已有摘要：\n${previousSummary}\n\n新对话：\n${dialogText}\n\n请输出两层摘要（按以下格式，不要加任何前缀）：\n### 关键决策\n（2-3句话：目的地、预算、偏好、行程安排、已做出的决定）\n### 对话脉络\n（2-3句话：讨论了哪些话题、用户感兴趣的方向、关注重点）`
    } else {
      systemMsg = '你是一个对话摘要助手。请分析以下对话，输出两层摘要。严格按格式输出。'
      prompt = `对话：\n${dialogText}\n\n请输出两层摘要（按以下格式，不要加任何前缀）：\n### 关键决策\n（2-3句话：目的地、预算、偏好、行程安排、已做出的决定）\n### 对话脉络\n（2-3句话：讨论了哪些话题、用户感兴趣的方向、关注重点）`
    }

    let summary: string | null = null
    let recap: string | null = null
    let lastError: unknown

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const llm = createLLM({ streaming: false, temperature: 0.3 })
        const response = await llm.invoke([
          new SystemMessage(systemMsg),
          new HumanMessage(prompt),
        ])
        const text = (response.content as string).trim()
        const decisionMatch = text.match(/###\s*关键决策\s*\n([\s\S]*?)(?=###\s*对话脉络|$)/)
        const flowMatch = text.match(/###\s*对话脉络\s*\n([\s\S]*)/)
        summary = decisionMatch?.[1]?.trim() || null
        recap = flowMatch?.[1]?.trim() || null
        if (summary && recap) break
        summary = null
        recap = null
      } catch (e) {
        lastError = e
        console.warn(`[Summary] 第 ${attempt + 1} 次压缩失败:`, e instanceof Error ? e.message : e)
        if (attempt < MAX_RETRIES) {
          await sleep(RETRY_BASE_MS * (attempt + 1))
        }
      }
    }

    if (summary && recap) {
      await commitSummary(conversationId, summary, recap, previousSummary)
    } else {
      // 降级：如果分层解析失败，至少保存决策摘要
      if (summary) {
        await commitSummary(conversationId, summary, '', previousSummary)
      } else {
        console.error(`[Summary] ${MAX_RETRIES + 1} 次重试全部失败，标记 summary_error`)
        await markSummaryFailed(conversationId)
      }
    }
  } catch (e) {
    console.error('[Summary] 压缩流程异常:', e instanceof Error ? e.message : e)
    await markSummaryFailed(conversationId).catch(() => {})
  }
}
