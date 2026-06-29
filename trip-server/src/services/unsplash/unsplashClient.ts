import { logger } from '../../utils/logger'
import { UNSPLASH_CONFIG } from '../../config/unsplash'

export interface UnsplashPhoto {
  url: string
  description: string
  photographer: string
}

export async function searchPhotos(query: string, perPage: number = 3): Promise<UnsplashPhoto[]> {
  if (!UNSPLASH_CONFIG.enabled) return []

  try {
    const url = `https://api.unsplash.com/search/photos?query=${encodeURIComponent(query)}&per_page=${perPage}&orientation=landscape&content_filter=high`
    const res = await fetch(url, {
      headers: { Authorization: `Client-ID ${UNSPLASH_CONFIG.accessKey}` },
      signal: AbortSignal.timeout(UNSPLASH_CONFIG.searchTimeoutMs),
    })
    if (!res.ok) {
      logger.warn({ status: res.status }, '[Unsplash] search failed')
      return []
    }
    const data = await res.json() as any
    if (!data.results?.length) return []

    return data.results.map((photo: any) => ({
      url: photo.urls?.regular || '',
      description: photo.description || photo.alt_description || '',
      photographer: photo.user?.name || 'Unknown',
    }))
  } catch (err) {
    logger.warn({ err }, '[Unsplash] search error')
    return []
  }
}

/** 简单 hash：把字符串转成 0..max-1 的索引 */
function simpleHash(s: string, max: number): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h) + s.charCodeAt(i)
  return Math.abs(h) % max
}

export async function searchPhoto(query: string): Promise<UnsplashPhoto | null> {
  const photos = await searchPhotos(query)
  return photos[0] ?? null
}

/** 按名称 hash 从搜索结果中选图，不同名字尽量选不同图 */
export async function searchPhotoByName(query: string, name: string): Promise<UnsplashPhoto | null> {
  const photos = await searchPhotos(query, 5)
  if (photos.length === 0) return null
  const idx = simpleHash(name, photos.length)
  return photos[idx]
}
