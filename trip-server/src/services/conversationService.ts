import prisma from '../config/database'
import { estimateTokens, getHistoryMaxTokens } from '../utils/tokens'

const SLIDING_WINDOW = 10

/**
 * 获取最近消息，按 token 总量限制（从最新往前取，不超 maxTokens）
 */
export async function getRecentMessagesByTokens(conversationId: number, maxTokens: number) {
  const messages = await prisma.message.findMany({
    where: { conversationId },
    orderBy: { createdAt: 'desc' },
  })

  let tokenCount = 0
  const result: typeof messages = []
  for (const msg of messages) {
    const tokens = estimateTokens(msg.content)
    if (tokenCount + tokens > maxTokens) break
    tokenCount += tokens
    result.unshift(msg)
  }
  return result
}

/**
 * 获取或创建对话会话
 */
export async function getOrCreateConversation(userId: number, conversationId?: number) {
  if (conversationId) {
    const existing = await prisma.conversation.findFirst({
      where: { id: conversationId, userId },
    })
    if (existing) return existing
  }
  return prisma.conversation.create({
    data: { userId, title: '新对话' },
  })
}

/**
 * 保存消息
 */
export async function saveMessage(conversationId: number, role: 'user' | 'assistant' | 'system', content: string, metadata?: any) {
  return prisma.message.create({
    data: { conversationId, role, content, metadata: metadata ?? undefined },
  })
}

/**
 * 获取最近 N 条消息（按时间正序）
 */
export async function getRecentMessages(conversationId: number, limit = SLIDING_WINDOW * 2) {
  const messages = await prisma.message.findMany({
    where: { conversationId },
    orderBy: { createdAt: 'desc' },
    take: limit,
  })
  return messages.reverse()
}

/**
 * 加载上下文：摘要 + 最近消息（token 限制）
 */
export async function loadContext(conversationId: number) {
  const maxTokens = getHistoryMaxTokens()
  const conversation = await prisma.conversation.findUnique({ where: { id: conversationId } })
  const systemSummary = conversation?.summary ?? null
  const recentMessages = await getRecentMessagesByTokens(conversationId, maxTokens)

  return { systemSummary, recentMessages }
}

/**
 * 更新对话摘要
 */
export async function updateSummary(conversationId: number, summary: string) {
  return prisma.conversation.update({
    where: { id: conversationId },
    data: { summary },
  })
}

/**
 * 自动生成标题
 */
export async function autoTitle(conversationId: number, firstUserMessage: string) {
  const title = firstUserMessage.slice(0, 20) + (firstUserMessage.length > 20 ? '...' : '')
  return prisma.conversation.update({
    where: { id: conversationId },
    data: { title },
  })
}

/**
 * 列出用户的对话
 */
export async function listConversations(userId: number, page = 1, pageSize = 20) {
  const [items, total] = await Promise.all([
    prisma.conversation.findMany({
      where: { userId },
      orderBy: { updatedAt: 'desc' },
      skip: (page - 1) * pageSize,
      take: pageSize,
      include: { _count: { select: { messages: true } } },
    }),
    prisma.conversation.count({ where: { userId } }),
  ])
  return { items, total, page, pageSize }
}

/**
 * 获取对话详情
 */
export async function getConversationDetail(conversationId: number, userId: number) {
  return prisma.conversation.findFirst({
    where: { id: conversationId, userId },
    include: { messages: { orderBy: { createdAt: 'asc' } } },
  })
}

/**
 * 删除对话
 */
export async function deleteConversation(conversationId: number, userId: number) {
  const conv = await prisma.conversation.findFirst({ where: { id: conversationId, userId } })
  if (!conv) throw new Error('对话不存在或无权访问')
  return prisma.conversation.delete({ where: { id: conversationId } })
}

export const MEMORY_CONFIG = {
  SLIDING_WINDOW,
}
