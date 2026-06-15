import prisma from '../config/database'
import { createLLM } from '../config/llm'
import { HumanMessage, SystemMessage } from '@langchain/core/messages'
import { updateSummary } from './conversationService'

const SLIDING_WINDOW = 10
const COMPRESS_THRESHOLD = SLIDING_WINDOW * 2

export async function compressConversation(conversationId: number): Promise<void> {
  try {
    const totalCount = await prisma.message.count({ where: { conversationId } })
    if (totalCount <= COMPRESS_THRESHOLD) return

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

    const llm = createLLM({ streaming: false, temperature: 0.3 })
    const response = await llm.invoke([
      new SystemMessage(
        '你是一个对话摘要助手。请用 2-3 句话概括以下对话，保留关键信息：目的地、预算、偏好、行程安排、已做出的决定。只输出摘要文本，不要加任何前缀。',
      ),
      new HumanMessage(`请概括以下对话：\n${dialogText}`),
    ])

    const summary = (response.content as string).trim()
    if (summary) {
      await updateSummary(conversationId, summary)
      console.log(`[Summary] 对话 ${conversationId} 摘要已更新 (${summary.length} 字)`)
    }
  } catch (e) {
    console.error('[Summary] 压缩失败:', e instanceof Error ? e.message : e)
  }
}
