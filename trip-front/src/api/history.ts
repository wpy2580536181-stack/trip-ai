import { get } from './request'

export interface TripListItem {
  id: number
  userId: number | null
  city: string
  days: number
  budget: number
  content: unknown
  status: string
  parentTripId: number | null
  createdAt: string
}

export interface TripDetail extends TripListItem {}

export async function listTrips(page = 1, pageSize = 20) {
  return get<{ items: TripListItem[]; total: number; page: number; pageSize: number }>(
    'history/trips',
    { page, pageSize },
  )
}

export async function getTrip(id: number) {
  return get<TripDetail>(`history/trips/${id}`)
}
