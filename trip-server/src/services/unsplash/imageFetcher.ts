import { logger } from '../../utils/logger'
import { UNSPLASH_CONFIG } from '../../config/unsplash'
import * as unsplashClient from './unsplashClient'
import * as unsplashCache from './unsplashCache'
import * as amapMcpClient from '../mcp/amapMcpClient'

function parseSpots(itinerary: any): Array<{ city: string; name: string }> {
  const spots: Array<{ city: string; name: string }> = []
  const city = itinerary?.city || ''
  const days = itinerary?.days || []
  for (const day of days) {
    for (const s of (day.spots || [])) {
      const name = s.name || s.spot
      if (name && city) spots.push({ city, name })
    }
  }
  return spots
}

function buildCacheKey(city: string, name: string): string {
  return `amap:${city}:${name}`
}

/** 用 Amap maps_text_search 查 POI 照片 URL */
async function fetchAmapPhoto(city: string, name: string): Promise<string | null> {
  try {
    const raw = await amapMcpClient.callTool('maps_text_search', { keywords: name, city })
    // 解析 JSON 响应，从 poi[0].photos.url 取图
    const data = JSON.parse(raw)
    const poi = data?.pois?.[0]
    if (poi?.photos?.url) {
      return poi.photos.url
    }
    return null
  } catch (err) {
    logger.warn({ err, city, name }, '[imageFetcher] Amap photo search failed')
    return null
  }
}

function buildSearchQuery(city: string, name: string): string {
  return `${name} ${city} landmark travel`.trim()
}

export async function fetchImages(itinerary: any): Promise<any> {
  if (!UNSPLASH_CONFIG.enabled || !itinerary) return itinerary

  const spots = parseSpots(itinerary)
  if (spots.length === 0) return itinerary

  const unique = new Map<string, typeof spots[0]>()
  for (const s of spots) unique.set(buildCacheKey(s.city, s.name), s)

  const pending = new Map<string, { city: string; name: string }>()

  for (const [, spot] of unique) {
    const key = buildCacheKey(spot.city, spot.name)
    const cached = unsplashCache.getCache(key)
    if (cached) {
      writeBack(itinerary, spot.name, cached)
    } else {
      pending.set(key, spot)
    }
  }

  if (pending.size === 0) return itinerary

  // 优先 Amap，无结果 fallback Unsplash
  const entries = [...pending.entries()]
  for (let i = 0; i < entries.length; i++) {
    const [key, spot] = entries[i]
    let photoUrl = await fetchAmapPhoto(spot.city, spot.name)
    if (!photoUrl) {
      // Fallback Unsplash
      const unsplashResult = await unsplashClient.searchPhotoByName(
        buildSearchQuery(spot.city, spot.name), spot.name
      )
      photoUrl = unsplashResult?.url ?? null
    }
    if (photoUrl) {
      unsplashCache.setCache(key, photoUrl, UNSPLASH_CONFIG.cacheTtlMs)
      writeBack(itinerary, spot.name, photoUrl)
    }
  }

  return itinerary
}

function writeBack(itinerary: any, spotName: string, url: string): void {
  for (const day of (itinerary.days || [])) {
    for (const s of (day.spots || [])) {
      const match = s.name || s.spot
      if (match === spotName && !s.imageUrl) s.imageUrl = url
    }
  }
}
