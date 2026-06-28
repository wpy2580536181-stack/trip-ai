import prisma from '../config/database'
import { estimateTokens, getHistoryMaxTokens } from '../utils/tokens'

const SLIDING_WINDOW = 10

export interface ContextMessages {
  /** 按时间正序的所有未压缩消息（excludedFromContext=false） */
  messages: Awaited<ReturnType<typeof prisma.message.findMany>>
  /** 当前 TAIL 累计 token 数 */
  totalTokens: number
  /** 累计 token 是否超过 maxTokens。true → 调用方应触发压缩 */
  needsCompaction: boolean
}

/**
 * 获取对话上下文消息（单调追加模式，不 shift）。
 *
 * 设计动机：保持 prefix 稳定以命中 LLM prompt cache。
 * - 返回所有未压缩的原始消息（按时间正序），让 LLM 看到完整 TAIL
 * - 仅返回 needsCompaction 标志告诉调用方"该压缩了"，由调用方决定压缩多少
 * - 已压缩的旧消息（excludedFromContext=true）从结果中过滤掉
 */
export async function getContextMessages(conversationId: number, maxTokens: number): Promise<ContextMessages> {
  const messages = await prisma.message.findMany({
    where: { conversationId, excludedFromContext: { not: true } },
    orderBy: { createdAt: 'asc' },
  })

  // 过滤掉 tripService 预创建的空 assistant 消息（content === ''）
  // 原因：tripService.chatStream() 在 agent 调用前先 create 一条空 assistant 消息占位
  // （给 AgentStep 拿 messageId），如果不过滤，turn 1 的 conversationHistory 就会
  // 包含这条空消息，chatPlannerNode 等"hasHistory = length > 0"判断会误判为多轮
  const realMessages = messages.filter((m) => m.content !== '')

  let totalTokens = 0
  for (const msg of realMessages) {
    totalTokens += estimateTokens(msg.content)
  }

  return {
    messages: realMessages,
    totalTokens,
    needsCompaction: totalTokens > maxTokens,
  }
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
 * 加载上下文：摘要 + 脉络 + 最近消息（token 限制）
 */
export async function loadContext(conversationId: number) {
  const maxTokens = getHistoryMaxTokens()
  const conversation = await prisma.conversation.findUnique({ where: { id: conversationId } })
  const systemSummary = conversation?.summary ?? null
  const conversationRecap = conversation?.recap ?? null
  const ctx = await getContextMessages(conversationId, maxTokens)

  return { systemSummary, conversationRecap, recentMessages: ctx.messages }
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
