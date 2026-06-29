<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, shallowRef } from 'vue'

export interface MapSpot {
  name: string
  description?: string
  latitude: number
  longitude: number
}

const props = withDefaults(defineProps<{
  spots: MapSpot[]
  height?: string
  zoom?: number
}>(), {
  height: '300px',
  zoom: 13,
})

const mapContainer = ref<HTMLElement>()
const mapInstance = shallowRef<any>(null)
const markers: any[] = []
let infoWindow: any = null
const loadError = ref(false)

async function initMap() {
  if (!mapContainer.value || props.spots.length === 0) return

  loadError.value = false

  const AMapLoader = (await import('@amap/amap-jsapi-loader')).default

  const loadOptions: Record<string, any> = {
    key: import.meta.env.VITE_AMAP_KEY || '',
    version: '2.0',
    plugins: ['AMap.Marker', 'AMap.InfoWindow'],
  }

  const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE
  if (securityCode) {
    loadOptions.securityJsCode = securityCode
  }

  let AMap: any
  try {
    AMap = await AMapLoader.load(loadOptions)
  } catch {
    loadError.value = true
    return
  }

  const map = new AMap.Map(mapContainer.value, {
    zoom: props.zoom,
    center: [props.spots[0].longitude, props.spots[0].latitude],
    mapStyle: 'amap://styles/light',
  })

  mapInstance.value = map

  props.spots.forEach((spot) => {
    const marker = new AMap.Marker({
      position: [spot.longitude, spot.latitude],
      title: spot.name,
    })
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

  if (props.spots.length > 1) {
    map.setFitView(markers, false, [40, 40, 40, 40])
  }
}

function destroyMap() {
  if (infoWindow) {
    infoWindow.close()
    infoWindow = null
  }
  markers.length = 0
  if (mapInstance.value) {
    mapInstance.value.destroy()
    mapInstance.value = null
  }
}

watch(() => props.spots.length, () => {
  destroyMap()
  initMap()
})

onMounted(initMap)
onUnmounted(destroyMap)
</script>

<template>
  <div v-if="spots.length > 0" ref="mapContainer" class="map-container" :style="{ height }" />
  <div v-else class="map-placeholder">暂无位置信息</div>
</template>

<style scoped>
.map-container {
  width: 100%;
  border-radius: 8px;
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
  border-radius: 8px;
}
</style>
