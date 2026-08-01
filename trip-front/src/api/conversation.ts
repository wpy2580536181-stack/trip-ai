import { get, del } from './request'

export interface ConversationListItem {
  id: number
  title: string | null
  createdAt: string
  updatedAt: string
  userId: number
  tripId: number | null
  _count: { messages: number }
}

export interface ConversationDetailMessage {
  id: number
  conversationId: number
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: unknown | null
  createdAt: string
}

export interface ConversationDetail {
  id: number
  userId: number
  tripId: number | null
  title: string | null
  summary: string | null
  createdAt: string
  updatedAt: string
  messages: ConversationDetailMessage[]
}

export interface ConversationByTripResponse {
  id: number
  userId: number
  tripId: number | null
  title: string | null
  summary: string | null
  summaryError: boolean | null
  summaryAt: string | null
  createdAt: string
  updatedAt: string | null
  messages: ConversationDetailMessage[]
}

export async function listConversations(page = 1, pageSize = 20) {
  return get<{ items: ConversationListItem[]; total: number; page: number; pageSize: number }>(
    'conversations',
    { page, pageSize },
  )
}

export async function getConversation(id: number) {
  return get<ConversationDetail>(`conversations/${id}`)
}

export async function getConversationByTripId(tripId: number) {
  return get<ConversationByTripResponse>(`conversations/by-trip/${tripId}`)
}

export async function deleteConversation(id: number) {
  return del<null>(`conversations/${id}`)
}
