/**
 * Feedback API
 *
 * 用户对单条 agent 消息提交 👍/👎 反馈
 * 后端文档：trip-server/src/routes/feedback.routes.ts
 */

import request from './request'

export type FeedbackRating = 1 | -1

export interface SubmitFeedbackParams {
  messageId: number
  conversationId: number
  rating: FeedbackRating
  comment?: string
  tags?: string[]
}

export interface MessageFeedbackStats {
  up: number
  down: number
  total: number
  satisfactionRate: number | null
}

export interface GlobalFeedbackStats {
  totalCount: number
  upCount: number
  downCount: number
  satisfactionRate: number
  recentDownComments: Array<{
    comment: string
    tags: string[] | null
    createdAt: string
  }>
}

export const submitFeedback = (params: SubmitFeedbackParams) =>
  request.post<{ id: number; rating: FeedbackRating }>('/api/feedback', params)

export const getMessageStats = (messageId: number) =>
  request.get<MessageFeedbackStats>(`/api/feedback/message/${messageId}`)

export const getGlobalStats = (days = 7) =>
  request.get<GlobalFeedbackStats>(`/api/feedback/stats?days=${days}`)
