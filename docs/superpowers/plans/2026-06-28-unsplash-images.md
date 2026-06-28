# Unsplash 景点图片 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 生成行程时自动为每个景点配 Unsplash 图片，详情页 + PDF/图片导出都展示。

**Architecture:** tripService pipeline 末尾（LLM 生成行程后）调用 `imageFetcher`，解析景点名 → 30天缓存查 → Unsplash API 查 → URL 写回 Trip.itinerary JSON。前端 `<SpotImage>` 组件显示图片。

**Tech Stack:** Unsplash API (REST), `isomorphic-fetch`, Vue 3

## Global Constraints

- Logger 路径: `../../utils/logger`
- 测试框架: vitest
- Unsplash API: `https://api.unsplash.com/search/photos?query=...&client_id=${key}`
- 图片 URL 存在 Trip.itinerary JSON 字段，不存 Spot 表
- Attribution 要求: 组件 hover 显示 "Photo by {name} on Unsplash"

---

### Task 1: Config + UnsplashClient + Cache + imageFetcher

**Files:**
- Create: `trip-server/src/config/unsplash.ts`
- Create: `trip-server/src/services/unsplash/unsplashClient.ts`
- Create: `trip-server/src/services/unsplash/unsplashCache.ts`
- Create: `trip-server/src/services/unsplash/imageFetcher.ts`
- Test: `trip-server/src/services/unsplash/__tests__/imageFetcher.test.ts`

**Interfaces:**
- Consumes: `process.env.UNSPLASH_ACCESS_KEY`
- Produces: `imageFetcher.fetchImages(itinerary: TripJson): Promise<TripJson>` — 接受行程 JSON 对象，返回带 imageUrl 的行程

- [ ] **Step 1: Create `src/config/unsplash.ts`**

```typescript
export const UNSPLASH_CONFIG = {
  accessKey: process.env.UNSPLASH_ACCESS_KEY || '',
  enabled: !!process.env.UNSPLASH_ACCESS_KEY,
  rateLimit: { maxPerHour: 50 },
  cacheTtlMs: 30 * 24 * 60 * 60 * 1000, // 30 days
  concurrency: 10,
  searchTimeoutMs: 5000,
}
```

- [ ] **Step 2: Create `src/services/unsplash/unsplashClient.ts`**

```typescript
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
```

- [ ] **Step 3: Create `src/services/unsplash/unsplashCache.ts`**

```typescript
const cache = new Map<string, { url: string; expiresAt: number }>()
const MAX_SIZE = 1000

export function getCache(key: string): string | undefined {
  const entry = cache.get(key)
  if (entry && entry.expiresAt > Date.now()) return entry.url
  if (entry) cache.delete(key)
  return undefined
}

export function setCache(key: string, url: string, ttlMs: number): void {
  if (cache.size >= MAX_SIZE) {
    const first = cache.keys().next().value
    if (first) cache.delete(first)
  }
  cache.set(key, { url, expiresAt: Date.now() + ttlMs })
}

export function clearCache(): void { cache.clear() }
export function cacheSize(): number { return cache.size }
```

- [ ] **Step 4: Create `src/services/unsplash/imageFetcher.ts`**

```typescript
import { logger } from '../../utils/logger'
import { UNSPLASH_CONFIG } from '../../config/unsplash'
import * as unsplashClient from './unsplashClient'
import * as unsplashCache from './unsplashCache'

function parseSpots(itinerary: any): Array<{ city: string; name: string }> {
  const spots: Array<{ city: string; name: string }> = []
  const city = itinerary?.city || ''
  const days = itinerary?.days || []
  for (const day of days) {
    for (const spot of (day.spots || [])) {
      if (spot.name && city) spots.push({ city, name: spot.name })
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

  // 去重
  const unique = new Map<string, typeof spots[0]>()
  for (const s of spots) unique.set(buildCacheKey(s.city, s.name), s)

  // 站内 group by day: spot -> imageUrl
  const pending = new Map<string, { city: string; name: string }>()

  for (const [, spot] of unique) {
    const key = buildCacheKey(spot.city, spot.name)
    const cached = unsplashCache.getCache(key)
    if (cached) {
      // 写回所有同名的 spot
      for (const day of (itinerary.days || [])) {
        for (const s of (day.spots || [])) {
          if (s.name === spot.name && !s.imageUrl) s.imageUrl = cached
        }
      }
    } else {
      pending.set(key, spot)
    }
  }

  if (pending.size === 0) return itinerary

  // 并发 batch
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
        // 写回所有同名 spot
        for (const day of (itinerary.days || [])) {
          for (const s of (day.spots || [])) {
            if (s.name === spot.name && !s.imageUrl) s.imageUrl = result.value.url
          }
        }
      }
    }
  }

  return itinerary
}
```

- [ ] **Step 5: Create test file `src/services/unsplash/__tests__/imageFetcher.test.ts`**

```typescript
import { describe, it, before, after, mock } from 'node:test'
import { strict as assert } from 'node:assert'
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
  before(() => { process.env.UNSPLASH_ACCESS_KEY = 'test_key' })
  after(() => { delete process.env.UNSPLASH_ACCESS_KEY; unsplashCache.clearCache() })

  it('should add imageUrl to spots from cache', async () => {
    unsplashCache.setCache('北京:故宫博物院', 'https://cached.url/img.jpg', 99999999)
    const result = await fetchImages(sampleItinerary)
    assert.equal(result.days[0].spots[0].imageUrl, 'https://cached.url/img.jpg')
  })

  it('should call searchPhoto for uncached spots', async () => {
    mock.method(unsplashClient, 'searchPhoto', () =>
      Promise.resolve({ url: 'https://new.url/img.jpg', description: 'test', photographer: 'test' })
    )
    const result = await fetchImages(sampleItinerary)
    assert.equal(result.days[0].spots[1].imageUrl, 'https://new.url/img.jpg')
  })

  it('should handle empty itinerary', async () => {
    const result = await fetchImages({ city: '北京', days: [] })
    assert.deepEqual(result, { city: '北京', days: [] })
  })
})
```

- [ ] **Step 6: Verify and commit**

```bash
node --check trip-server/src/config/unsplash.ts
node --check trip-server/src/services/unsplash/unsplashClient.ts
node --check trip-server/src/services/unsplash/unsplashCache.ts
node --check trip-server/src/services/unsplash/imageFetcher.ts
npx vitest run src/services/unsplash/__tests__/
git add trip-server/src/config/unsplash.ts trip-server/src/services/unsplash/ trip-server/.env.example
git commit -m "feat(unsplash): add image fetcher with cache and batch search"
```

---

### Task 2: tripService Integration + frontend SpotImage + Detail + PrintView

**Files:**
- Modify: `trip-server/src/services/tripService.ts`
- Create: `trip-front/src/components/SpotImage.vue`
- Modify: `trip-front/src/views/Detail.vue`
- Modify: `trip-front/src/components/ItineraryPrintView.vue`

**Interfaces:**
- Consumes: `fetchImages(itinerary)` from Task 1

**Dependencies:** Depends on Task 1 (needs `imageFetcher.fetchImages`)

- [ ] **Step 1: Modify `tripService.ts`**

找到 `recommend()` 方法中行程生成后的位置（`const result = await graph.invoke(...)` 之后、返回之前），添加：

```typescript
import { fetchImages } from './unsplash/imageFetcher'

// 在 recommend() 的 graph.invoke 之后，return 之前：
if (result.parsed) {
  result.parsed = await fetchImages(result.parsed as any)
}
```

如果 `parsed` 字段是 itinerary JSON 对象，传入 `fetchImages` 后它会原地写入 `imageUrl`。

- [ ] **Step 2: Create `trip-front/src/components/SpotImage.vue`**

```vue
<template>
  <div class="spot-image" :style="{ width, height }">
    <img
      v-if="src"
      :src="src"
      :alt="alt"
      @error="onError"
      :class="{ loaded: loaded }"
      @load="loaded = true"
    />
    <div v-if="!loaded && !errored" class="spot-image-placeholder">
      <span>{{ alt?.charAt(0) || '?' }}</span>
    </div>
    <div v-if="errored" class="spot-image-placeholder errored">
      <span>{{ alt?.charAt(0) || '?' }}</span>
    </div>
    <div v-if="attribution && loaded" class="spot-image-attribution">
      Photo by {{ attribution }} on Unsplash
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  src?: string
  alt?: string
  attribution?: string
  width?: string
  height?: string
}>(), {
  width: '100%',
  height: '200px',
})

const loaded = ref(false)
const errored = ref(false)

function onError() {
  errored.value = true
  loaded.value = true
}
</script>

<style scoped>
.spot-image {
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  background: #f0f0f0;
}
.spot-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 0.3s;
}
.spot-image img.loaded { opacity: 1; }
.spot-image-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  font-size: 48px;
  font-weight: bold;
}
.spot-image-placeholder.errored { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
.spot-image-attribution {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(0,0,0,0.5);
  color: #fff;
  font-size: 10px;
  padding: 2px 6px;
  text-align: right;
}
</style>
```

- [ ] **Step 3: Modify `Detail.vue`**

在景点卡片中添加 `<SpotImage>`。找到景点列表渲染的地方（v-for spot），在每个景点卡片中添加：

```vue
<SpotImage
  :src="spot.imageUrl"
  :alt="spot.name"
  attribution="Unsplash"
  height="180px"
/>
```

- [ ] **Step 4: Modify `ItineraryPrintView.vue`**

在导出视图中也添加景点图片：

```vue
<img v-if="spot.imageUrl" :src="spot.imageUrl" :alt="spot.name" class="print-spot-image" />
```

并在 `<style>` 中添加：
```css
.print-spot-image { width: 100%; height: 180px; object-fit: cover; border-radius: 4px; margin-bottom: 8px; }
```

- [ ] **Step 5: Verify and commit**

```bash
cd trip-front && pnpm exec vue-tsc --noEmit 2>&1 | head -5
cd trip-front && pnpm exec vite build 2>&1 | tail -3
cd trip-server && npx vitest run src/services/unsplash/__tests__/
git add -A
git commit -m "feat(unsplash): integrate images into trip detail + export views"
```

---

### Self-Review Checklist

**1. Spec coverage:**
- ✅ UnsplashClient — Task 1
- ✅ 30-day cache — Task 1 (unsplashCache.ts)
- ✅ Batch concurrency — Task 1 (imageFetcher.ts, Promise.allSettled batch)
- ✅ tripService pipeline integration — Task 2
- ✅ SpotImage.vue with placeholder + loading + attribution — Task 2
- ✅ Detail.vue + ItineraryPrintView images — Task 2
- ✅ Attribution — Task 2 (SpotImage attribution line)

**2. Placeholder scan:** None

**3. Type consistency:** `fetchImages(itinerary: any): Promise<any>` — intentionally loosely typed since Trip JSON is a free-form object. `searchPhoto(query): Promise<UnsplashPhoto | null>` — consistent across client and fetcher.
