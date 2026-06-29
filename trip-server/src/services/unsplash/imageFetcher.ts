import { logger } from '../../utils/logger'
import { UNSPLASH_CONFIG } from '../../config/unsplash'
import * as unsplashClient from './unsplashClient'
import * as unsplashCache from './unsplashCache'

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
  return `${city}:${name}`
}

function buildSearchQuery(city: string, name: string): string {
  return `${name} ${city}`.trim()
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
      for (const day of (itinerary.days || [])) {
        for (const s of (day.spots || [])) {
          const match = s.name || s.spot
          if (match === spot.name && !s.imageUrl) s.imageUrl = cached
        }
      }
    } else {
      pending.set(key, spot)
    }
  }

  if (pending.size === 0) return itinerary

  const entries = [...pending.entries()]
  const batchSize = UNSPLASH_CONFIG.concurrency
  for (let i = 0; i < entries.length; i += batchSize) {
    const batch = entries.slice(i, i + batchSize)
    const results = await Promise.allSettled(
      batch.map(([, spot]) =>
        unsplashClient.searchPhoto(buildSearchQuery(spot.city, spot.name))
      )
    )
    for (let j = 0; j < batch.length; j++) {
      const [key, spot] = batch[j]
      const result = results[j]
      if (result.status === 'fulfilled' && result.value) {
        unsplashCache.setCache(key, result.value.url, UNSPLASH_CONFIG.cacheTtlMs)
        for (const day of (itinerary.days || [])) {
          for (const s of (day.spots || [])) {
            const match = s.name || s.spot
            if (match === spot.name && !s.imageUrl) s.imageUrl = result.value.url
          }
        }
      }
    }
  }

  return itinerary
}
