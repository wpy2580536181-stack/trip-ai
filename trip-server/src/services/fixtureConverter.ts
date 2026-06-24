/**
 * Fixture 转换器
 *
 * 把"在线负反馈"序列化成 eval fixture YAML 骨架。
 * admin 收到后手动补 expected 段（must_contain_keywords 等）。
 *
 * 关键设计：
 * - input.message 选 < targetMessageId 的最后 user turn（不是 assistant 自身）
 * - history 包含 target message 之前的所有轮次（user + assistant）
 * - content 截断 10KB 防止 fixture 膨胀
 * - id slugify 兼容中文/英文/数字
 */

import * as yaml from 'js-yaml'

const MAX_CONTENT_LENGTH = 10000

export interface ConvertInput {
  feedbackId: number
  feedbackComment: string | null
  feedbackTags: string[] | null
  feedbackCreatedAt: Date
  messageId: number
  messageContent: string
  userId: number
  username: string
  userPreferences: Record<string, any> | null
  /** 整段 conversation 的 messages（含 user/assistant），按 createdAt 升序 */
  conversationMessages: Array<{
    id: number
    role: 'user' | 'assistant'
    content: string
    createdAt: Date
  }>
}

export function slugify(text: string): string {
  return text
    .slice(0, 30)
    .replace(/[^\w\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase() || 'untitled'
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text
  return text.slice(0, max) + '...[已截断]'
}

function pickInputMessage(
  msgs: ConvertInput['conversationMessages'],
  targetId: number
): string {
  const earlier = msgs.filter((m) => m.id < targetId)
  const lastUser = [...earlier].reverse().find((m) => m.role === 'user')
  return lastUser?.content ?? ''
}

function pickHistory(
  msgs: ConvertInput['conversationMessages'],
  targetId: number
): Array<{ role: 'user' | 'assistant'; content: string }> {
  return msgs
    .filter((m) => m.id < targetId)
    .map((m) => ({ role: m.role, content: truncate(m.content, MAX_CONTENT_LENGTH) }))
}

export function toYAML(input: ConvertInput): string {
  const inputMessage = truncate(pickInputMessage(input.conversationMessages, input.messageId), MAX_CONTENT_LENGTH)
  const history = pickHistory(input.conversationMessages, input.messageId)
  const userSlug = slugify(input.username).slice(0, 20)
  const msgSlug = slugify(inputMessage).slice(0, 30)

  const fixture: Record<string, any> = {
    id: `feedback-${input.feedbackId}-${userSlug}-${msgSlug}`,
    description: `来自生产反馈 #${input.feedbackId}：${input.feedbackComment?.slice(0, 50) || '(无评论)'}`,
    tags: ['feedback-imported', 'user-reported', ...(input.feedbackTags || [])],
    source: {
      feedback_id: input.feedbackId,
      message_id: input.messageId,
      user: input.username,
      created_at: input.feedbackCreatedAt.toISOString(),
      original_comment: input.feedbackComment || null,
    },
    input: {
      message: inputMessage,
      preferences: input.userPreferences || {},
      history,
    },
    expected: {
      must_contain_keywords: [],
      must_not_contain_keywords: [],
    },
    evaluators: ['schema_check', 'keyword_coverage'],
  }

  return yaml.dump(fixture, {
    lineWidth: 120,
    noRefs: true,
    quotingType: '"',
  })
}
