import { post, get } from './request'

export type CommuteMode = 'driving' | 'walking' | 'transit' | 'cycling'

export interface CommuteCandidate {
  id?: string
  name: string
  lat?: number
  lng?: number
  city?: string
  address?: string
}

export interface TransitStepDetail {
  type: 'walking' | 'subway' | 'bus' | 'transfer_walk'
  label: string
  distance_m?: number | null
  duration_sec?: number | null
  departure?: string | null
  arrival?: string | null
  via_stops?: number | null
}

export interface CommuteResultItem {
  id?: string
  name: string
  duration_sec: number
  distance_m: number
  transfers?: number | null
  polyline?: string | null
  polyline_segments?: string[] | null
  lat?: number | null
  lng?: number | null
  has_subway?: boolean | null
  transit_lines?: string[] | null
  steps_detail?: TransitStepDetail[] | null
  per_mode?: Record<
    string,
    { duration_sec?: number | null; distance_m?: number | null; error?: string | null }
  > | null
  error?: string | null
}

export interface CommuteResponse {
  origin: { lat: number; lng: number }
  mode: CommuteMode
  results: CommuteResultItem[]
  recommended: CommuteResultItem | null
  errors: { name?: string; error?: string }[]
}

// ---------------------------------------------------------------------------
// 联想结果
// ---------------------------------------------------------------------------

export interface InputTipItem {
  name: string
  address: string | null
  district: string | null
  lat: number | null
  lng: number | null
}

/** 地址输入联想（高德 inputtips） */
export function fetchInputTips(keywords: string, city?: string) {
  return get<{ tips: InputTipItem[] }>('/commute/inputtips', {
    keywords,
    ...(city ? { city } : {}),
  })
}

/** 地址地理编码（高德 geocode/geo），返回经纬度 */
export function geocodeAddress(address: string, city?: string) {
  return get<{ lat: number | null; lng: number | null; found: boolean }>(
    '/commute/geocode',
    { address, ...(city ? { city } : {}) },
  )
}

// ---------------------------------------------------------------------------
// 周边 POI 推荐
// ---------------------------------------------------------------------------

export interface NearbyPoi {
  name: string
  address?: string | null
  category?: string | null
  distance?: number | null
  lat: number
  lng: number
}

/** 周边 POI 推荐（高德 place/around） */
export function fetchNearby(params: {
  lat: number
  lng: number
  radius?: number
  keywords?: string
}) {
  return get<{ pois: NearbyPoi[] }>('/commute/nearby', params)
}

// ---------------------------------------------------------------------------
// 核心
// ---------------------------------------------------------------------------

/** 计算从当前位置到各候选目的地的最短通勤 */
export function computeOptimal(payload: {
  origin: { lat: number; lng: number }
  destinations: CommuteCandidate[]
  mode: CommuteMode
  city?: string
  compare_modes?: boolean
  waypoints?: CommuteCandidate[]
}) {
  return post<CommuteResponse>('/commute/optimal', payload)
}
