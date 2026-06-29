import { logger as log } from '../utils/logger'

const GEOCODE_URL = 'https://restapi.amap.com/v3/geocode/geo'
const BATCH_SIZE = 10
const RATE_LIMIT_MS = 50

interface GeocodeResult {
  lat: number
  lng: number
}

interface PendingItem {
  spotName: string
  city: string
  resolve: (result: GeocodeResult | null) => void
}

let pendingQueue: PendingItem[] = []
let timer: NodeJS.Timeout | null = null

function flushQueue() {
  const batch = pendingQueue.splice(0, BATCH_SIZE)
  pendingQueue = []

  if (batch.length === 0) return

  Promise.allSettled(
    batch.map(async (item) => {
      try {
        const result = await geocodeSingle(item.spotName, item.city)
        item.resolve(result)
      } catch {
        item.resolve(null)
      }
    })
  )
}

function enqueue(spotName: string, city: string): Promise<GeocodeResult | null> {
  return new Promise((resolve) => {
    pendingQueue.push({ spotName, city, resolve })
    if (!timer) {
      timer = setTimeout(() => {
        timer = null
        flushQueue()
      }, RATE_LIMIT_MS)
    }
  })
}

async function geocodeSingle(spotName: string, city: string): Promise<GeocodeResult | null> {
  const apiKey = process.env.GAODE_API_KEY
  if (!apiKey) {
    log.warn('GAODE_API_KEY not configured, skipping geocoding')
    return null
  }

  const url = `${GEOCODE_URL}?key=${apiKey}&address=${encodeURIComponent(spotName)}&city=${encodeURIComponent(city)}&output=JSON`

  try {
    const res = await fetch(url)
    const data = await res.json() as { status: string; geocodes?: { location: string }[] }

    if (data.status === '1' && data.geocodes && data.geocodes.length > 0) {
      const [lng, lat] = data.geocodes[0].location.split(',').map(Number)
      if (!isNaN(lat) && !isNaN(lng)) {
        return { lat, lng }
      }
    }
    return null
  } catch (err) {
    log.error({ err, spotName, city }, 'geocode failed')
    return null
  }
}

export async function geocodeSpot(spotName: string, city: string): Promise<GeocodeResult | null> {
  return enqueue(spotName, city)
}

export async function enrichTripWithGeocoding(tripData: {
  city: string
  dailyItinerary: { morning: any; afternoon: any; evening: any }[]
}): Promise<void> {
  const { city, dailyItinerary } = tripData
  if (!dailyItinerary || dailyItinerary.length === 0) return

  const slots: { spotName: string; slot: any }[] = []
  for (const day of dailyItinerary) {
    for (const period of ['morning', 'afternoon', 'evening'] as const) {
      const slot = day[period]
      if (slot && slot.spot) {
        slots.push({ spotName: slot.spot, slot })
      }
    }
  }

  const batchSize = 10
  for (let i = 0; i < slots.length; i += batchSize) {
    const batch = slots.slice(i, i + batchSize)
    await Promise.all(
      batch.map(async ({ spotName, slot }) => {
        if (slot.latitude != null && slot.longitude != null) return
        const result = await geocodeSpot(spotName, city)
        if (result) {
          slot.latitude = result.lat
          slot.longitude = result.lng
        }
      })
    )
  }
}
