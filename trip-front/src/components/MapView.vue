<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, shallowRef } from 'vue'

export interface MapSpot {
  id?: string | number
  name: string
  description?: string
  latitude: number
  longitude: number
}

const props = withDefaults(
  defineProps<{
    spots: MapSpot[]
    height?: string
    zoom?: number
    /** 开启后点击地图会 emit pick 事件（带 {lat,lng}），用于选点 */
    selectable?: boolean
    /** 高德 v5 polyline 字符串数组（"lng,lat;lng,lat;..."），绘制推荐路线 */
    routes?: string[]
    /** 标记哪个 spot 是当前起点（特殊样式） */
    originId?: string | number
  }>(),
  {
    height: '300px',
    zoom: 13,
    selectable: false,
    routes: () => [],
  },
)

const emit = defineEmits<{
  (e: 'pick', payload: { lat: number; lng: number }): void
}>()

const mapContainer = ref<HTMLElement>()
const mapInstance = shallowRef<any>(null)
const markers: any[] = []
const routeOverlays: any[] = []
let infoWindow: any = null
let clickHandler: ((e: any) => void) | null = null
const loadError = ref(false)

/** 解析高德 v5 polyline：经纬度对以 ';' 分隔 */
function decodePolyline(poly: string): [number, number][] {
  try {
    return poly
      .split(';')
      .map((p) => {
        const [lng, lat] = p.split(',').map(Number)
        return [lng, lat] as [number, number]
      })
      .filter((c) => !Number.isNaN(c[0]) && !Number.isNaN(c[1]))
  } catch {
    return []
  }
}

async function initMap() {
  if (!mapContainer.value) return
  loadError.value = false

  const AMapLoader = (await import('@amap/amap-jsapi-loader')).default
  const loadOptions: Record<string, any> = {
    key: import.meta.env.VITE_AMAP_KEY || '',
    version: '2.0',
    plugins: ['AMap.Marker', 'AMap.InfoWindow'],
  }
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE
  if (securityCode) loadOptions.securityJsCode = securityCode

  let AMap: any
  try {
    AMap = await AMapLoader.load(loadOptions as any)
  } catch {
    loadError.value = true
    return
  }

  const center = props.spots.length
    ? [props.spots[0].longitude, props.spots[0].latitude]
    : [116.397, 39.909] // 无点时默认北京，便于选点

  const map = new AMap.Map(mapContainer.value, {
    zoom: props.zoom,
    center,
    mapStyle: 'amap://styles/light',
  })
  mapInstance.value = map

  if (props.selectable) {
    clickHandler = (e: any) => {
      const lnglat = e.lnglat
      emit('pick', { lng: lnglat.getLng(), lat: lnglat.getLat() })
    }
    map.on('click', clickHandler)
  }

  props.spots.forEach((spot) => {
    const isOrigin =
      props.originId != null && spot.id != null && spot.id === props.originId
    const marker = new AMap.Marker({
      position: [spot.longitude, spot.latitude],
      title: spot.name,
    })
    if (isOrigin) {
      marker.setLabel({
        content: '🚩 起点',
        direction: 'top',
        offset: new AMap.Pixel(0, -4),
        zIndex: 200,
      })
    } else if (spot.name) {
      // 目的地标记：纯文字标签，避免高德默认白框
      marker.setLabel({
        content: spot.name,
        direction: 'top',
        offset: new AMap.Pixel(0, -4),
        zIndex: 100,
      })
    }
    marker.on('click', () => {
      if (infoWindow) infoWindow.close()
      infoWindow = new AMap.InfoWindow({
        content: `<div style="padding:4px 0;max-width:240px;font-size:13px;line-height:1.5">
          <strong style="font-size:14px;color:#333">${spot.name}</strong>
          ${spot.description ? `<p style="margin:4px 0 0;color:#666">${spot.description}</p>` : ''}
        </div>`,
        offset: new AMap.Pixel(0, -30),
      })
      infoWindow.open(map, [spot.longitude, spot.latitude])
    })
    markers.push(marker)
  })
  map.add(markers)

  // 绘制路线
  ;(props.routes || []).forEach((poly) => {
    const path = decodePolyline(poly)
    if (path.length > 1) {
      const line = new AMap.Polyline({
        path,
        strokeColor: '#665CA2',
        strokeWeight: 6,
        strokeOpacity: 0.85,
        showDir: true,
      })
      map.add(line)
      routeOverlays.push(line)
    }
  })

  const fitTargets = [...markers, ...routeOverlays]
  if (fitTargets.length > 1) {
    map.setFitView(fitTargets, false, [40, 40, 40, 40])
  }
}

function destroyMap() {
  if (infoWindow) {
    infoWindow.close()
    infoWindow = null
  }
  if (clickHandler && mapInstance.value) {
    mapInstance.value.off('click', clickHandler)
    clickHandler = null
  }
  markers.length = 0
  routeOverlays.length = 0
  if (mapInstance.value) {
    mapInstance.value.destroy()
    mapInstance.value = null
  }
}

watch(
  () => [props.spots, props.selectable, props.routes, props.originId],
  () => {
    destroyMap()
    initMap()
  },
)

onMounted(initMap)
onUnmounted(destroyMap)
</script>

<template>
  <div v-if="spots.length > 0 || selectable" ref="mapContainer" class="map-container" :style="{ height }" />
  <div v-else class="map-placeholder">暂无位置信息</div>
</template>

<style scoped>
.map-container {
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
}
.map-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: var(--text-secondary, #999);
  font-size: 14px;
  background: var(--bg-secondary, #f5f5f5);
  border-radius: 12px;
}
</style>
