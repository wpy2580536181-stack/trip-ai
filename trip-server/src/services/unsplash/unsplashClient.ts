import { logger } from '../../utils/logger'
import { UNSPLASH_CONFIG } from '../../config/unsplash'

export interface UnsplashPhoto {
  url: string
  description: string
  photographer: string
}

export async function searchPhoto(query: string): Promise<UnsplashPhoto | null> {
  if (!UNSPLASH_CONFIG.enabled) return null

  try {
    const url = `https://api.unsplash.com/search/photos?query=${encodeURIComponent(query)}&per_page=1&orientation=landscape&content_filter=high`
    const res = await fetch(url, {
      headers: { Authorization: `Client-ID ${UNSPLASH_CONFIG.accessKey}` },
      signal: AbortSignal.timeout(UNSPLASH_CONFIG.searchTimeoutMs),
    })
    if (!res.ok) {
      logger.warn({ status: res.status }, '[Unsplash] search failed')
      return null
    }
    const data = await res.json() as any
    if (!data.results?.length) return null

    const photo = data.results[0]
    return {
      url: photo.urls?.regular || '',
      description: photo.description || photo.alt_description || '',
      photographer: photo.user?.name || 'Unknown',
    }
  } catch (err) {
    logger.warn({ err }, '[Unsplash] search error')
    return null
  }
}
