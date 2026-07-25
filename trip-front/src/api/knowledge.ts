import { get, post, put, del } from './request'

export interface SpotItem {
  id: number
  name: string
  city: string
  category: string
  description: string
  tags: string[]
  avgCost: number | null
  duration: string | null
  openTime: string | null
  rating: number | null
  createdAt: string
  updatedAt: string
}

export interface SpotInput {
  name: string
  city: string
  category: string
  description: string
  tags?: string[]
  avgCost?: number
  duration?: string
  openTime?: string
  rating?: number
}

export async function listSpots(params?: {
  city?: string
  category?: string
  page?: number
  pageSize?: number
}) {
  return get<{ items: SpotItem[]; total: number; page: number; pageSize: number }>(
    'knowledge/spots',
    params,
  )
}

export async function getSpot(id: number) {
  return get<SpotItem>(`knowledge/spots/${id}`)
}

export async function createSpot(data: SpotInput) {
  return post<SpotItem>('knowledge/spots', data)
}

export async function updateSpot(id: number, data: Partial<SpotInput>) {
  return put<SpotItem>(`knowledge/spots/${id}`, data)
}

export async function deleteSpot(id: number) {
  return del<{ message: string }>(`knowledge/spots/${id}`)
}

export interface SpotDocItem {
  id: number
  spotId: number
  spotName: string | null
  city: string | null
  sourceType: string
  sourceName: string | null
  sourceUrl: string | null
  title: string | null
  content: string
  chunkIndex: number
  credibilityScore: number | null
  vectorId: string | null
  retrievedAt: string | null
}

export async function listSpotDocs(params?: {
  city?: string
  sourceType?: string
  page?: number
  pageSize?: number
}) {
  return get<{
    items: SpotDocItem[]
    total: number
    page: number
    pageSize: number
    chroma?: { available: boolean; spotDocsCount: number | null }
  }>(
    'knowledge/spot-docs',
    params,
  )
}
