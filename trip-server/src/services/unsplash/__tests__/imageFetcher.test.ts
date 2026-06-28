import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.hoisted(() => {
  process.env.UNSPLASH_ACCESS_KEY = 'test_key'
})

import { fetchImages } from '../imageFetcher'
import * as unsplashClient from '../unsplashClient'
import * as unsplashCache from '../unsplashCache'

const sampleItinerary = {
  city: '北京',
  days: [{
    date: '2026-07-01',
    spots: [
      { name: '故宫博物院', description: '故宫' },
      { name: '天安门广场', description: '天安门' },
    ],
  }],
}

describe('imageFetcher', () => {
  beforeEach(() => {
    unsplashCache.clearCache()
  })

  afterEach(() => {
    unsplashCache.clearCache()
    vi.restoreAllMocks()
  })

  it('should add imageUrl to spots from cache', async () => {
    unsplashCache.setCache('北京:故宫博物院', 'https://cached.url/img.jpg', 99999999)
    const result = await fetchImages(sampleItinerary)
    expect(result.days[0].spots[0].imageUrl).toBe('https://cached.url/img.jpg')
  })

  it('should call searchPhoto for uncached spots', async () => {
    vi.spyOn(unsplashClient, 'searchPhoto').mockImplementation(() =>
      Promise.resolve({ url: 'https://new.url/img.jpg', description: 'test', photographer: 'test' })
    )
    const result = await fetchImages(sampleItinerary)
    expect(result.days[0].spots[1].imageUrl).toBe('https://new.url/img.jpg')
  })

  it('should handle empty itinerary', async () => {
    const result = await fetchImages({ city: '北京', days: [] })
    expect(result).toEqual({ city: '北京', days: [] })
  })
})
