<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  NCard,
  NRadioGroup,
  NRadioButton,
  NInput,
  NButton,
  NList,
  NListItem,
  NThing,
  NTag,
  NDrawer,
  NDrawerContent,
  NCheckboxGroup,
  NCheckbox,
  NEmpty,
  NSpin,
  NAlert,
  NSpace,
  NText,
  NDivider,
  NAutoComplete,
  useMessage,
} from 'naive-ui'
import { get } from '../api/request'
import {
  computeOptimal,
  fetchInputTips,
  geocodeAddress,
  type CommuteMode,
  type CommuteCandidate,
  type CommuteResultItem,
  type InputTipItem,
} from '../api/commute'
import MapView, { type MapSpot } from '../components/MapView.vue'

const message = useMessage()

// ---------------------------------------------------------------------------
// 状态
// ---------------------------------------------------------------------------
const mode = ref<CommuteMode>('driving')
const city = ref('')
const origin = ref<{ lat: number; lng: number } | null>(null)
const originName = ref('')
const locating = ref(false)
const pickTarget = ref<'origin' | 'destination' | null>(null)

const candidates = ref<CommuteCandidate[]>([])
const searchName = ref('')
const inputTips = ref<InputTipItem[]>([])
const tipsLoading = ref(false)
const tipsTimer = ref<number | null>(null)

const loading = ref(false)
const results = ref<CommuteResultItem[] | null>(null)
const recommended = ref<CommuteResultItem | null>(null)
const errors = ref<{ name?: string; error?: string }[]>([])

const poiDrawer = ref(false)
const poiLoading = ref(false)
const poiList = ref<{ id: number; name: string; city: string; category?: string }[]>([])
const poiChecked = ref<number[]>([])

const modeOptions = [
  { label: '驾车', value: 'driving' },
  { label: '公交', value: 'transit' },
  { label: '步行', value: 'walking' },
  { label: '骑行', value: 'cycling' },
]

// ---------------------------------------------------------------------------
// 派生
// ---------------------------------------------------------------------------
const mapSpots = computed<MapSpot[]>(() => {
  const spots: MapSpot[] = []
  if (origin.value) {
    spots.push({
      id: 'origin',
      name: originName.value || '我的位置',
      latitude: origin.value.lat,
      longitude: origin.value.lng,
    })
  }
  candidates.value.forEach((c, i) => {
    if (typeof c.lat === 'number' && typeof c.lng === 'number') {
      spots.push({ id: `c${i}`, name: c.name, latitude: c.lat, longitude: c.lng })
    }
  })
  return spots
})

const originSpotId = computed(() => (origin.value ? 'origin' : undefined))
const routePolylines = computed(() =>
  recommended.value?.polyline ? [recommended.value.polyline] : [],
)

// 推荐项相对「次优项」快多少秒（无次优或推荐非最快则为 null）
const comparisonDiff = computed<number | null>(() => {
  if (!results.value || results.value.length < 2 || !recommended.value) return null
  const diff = results.value[1].duration_sec - recommended.value.duration_sec
  return diff > 0 ? diff : null
})

// 是否因高德限流导致部分候选失败（提示更友好）
const hasQpsError = computed(() =>
  errors.value.some((e) => /CUQPS|EXCEEDED|限流|配额/i.test(e.error || '')),
)

// 「时间最短 ≠ 最划算」权衡提示：公交模式下，若推荐项换乘更多，
// 提示次优项仅多几分钟却少换乘，体验可能更好。
const tradeoffHint = computed<string | null>(() => {
  if (mode.value !== 'transit') return null
  if (!results.value || results.value.length < 2 || !recommended.value) return null
  const rec = recommended.value
  const second = results.value[1]
  const recTransfers = rec.transfers ?? 0
  const secTransfers = second.transfers ?? 0
  if (recTransfers > secTransfers) {
    const diffSec = second.duration_sec - rec.duration_sec
    const less = recTransfers - secTransfers
    return `推荐项最快，但次优项仅多 ${formatDuration(diffSec)}、少换乘 ${less} 次，体验可能更好`
  }
  return null
})

// ---------------------------------------------------------------------------
// 方法
// ---------------------------------------------------------------------------
function detectLocation() {
  if (!('geolocation' in navigator)) {
    message.error('当前浏览器不支持定位')
    return
  }
  locating.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      origin.value = { lat: pos.coords.latitude, lng: pos.coords.longitude }
      originName.value = '我的位置'
      locating.value = false
    },
    (err) => {
      locating.value = false
      message.error('定位失败：' + (err.message || '请检查浏览器定位权限'))
    },
    { enableHighAccuracy: true, timeout: 10000 },
  )
}

function onPick(p: { lat: number; lng: number }) {
  if (pickTarget.value === 'origin') {
    origin.value = { lat: p.lat, lng: p.lng }
    originName.value = '地图选点'
    pickTarget.value = null
    message.success('已设置起点')
  } else {
    candidates.value = [
      ...candidates.value,
      { name: `点选位置 ${candidates.value.length + 1}`, lat: p.lat, lng: p.lng },
    ]
    pickTarget.value = null
    message.success('已添加候选点')
  }
}

async function addBySearch() {
  const name = searchName.value.trim()
  if (!name) {
    message.warning('请输入地点名称或地址')
    return
  }
  const cand: CommuteCandidate = { name }
  if (city.value) cand.city = city.value
  // 立即地理编码：让候选点马上出现在地图上；失败也不阻断（计算阶段后端再试）
  try {
    const res: any = await geocodeAddress(name, city.value || undefined)
    if (res?.found && res.lat != null && res.lng != null) {
      cand.lat = res.lat
      cand.lng = res.lng
    } else {
      message.warning('未匹配到坐标，将按名称计算（地图上稍后显示）')
    }
  } catch {
    // 编码异常静默，交给计算阶段兜底
  }
  candidates.value = [...candidates.value, cand]
  searchName.value = ''
  inputTips.value = []
}

function onSearchInput(val: string) {
  if (tipsTimer.value) window.clearTimeout(tipsTimer.value)
  const q = (val || '').trim()
  if (q.length < 2) {
    inputTips.value = []
    return
  }
  tipsLoading.value = true
  // 轻量防抖，避免逐字符请求触发高德限流
  tipsTimer.value = window.setTimeout(async () => {
    try {
      const res: any = await fetchInputTips(q, city.value || undefined)
      inputTips.value = res?.tips || []
    } catch {
      // 联想失败静默，不影响手动输入
      inputTips.value = []
    } finally {
      tipsLoading.value = false
    }
  }, 250)
}

function onSelectTip(tip: InputTipItem) {
  searchName.value = tip.name
  // 如果有坐标直接填入（省去后端地理编码）
  const cand: CommuteCandidate = { name: tip.name }
  if (tip.lat != null && tip.lng != null) {
    cand.lat = tip.lat
    cand.lng = tip.lng
  }
  if (city.value) cand.city = city.value
  candidates.value = [...candidates.value, cand]
  searchName.value = ''
  inputTips.value = []
}

function removeCandidate(i: number) {
  candidates.value = candidates.value.filter((_, idx) => idx !== i)
}

async function openPoi() {
  poiDrawer.value = true
  if (poiList.value.length || poiLoading.value) return
  poiLoading.value = true
  try {
    const res: any = await get('/knowledge/spots', { page: 1, pageSize: 100 })
    poiList.value = res?.data?.items || []
  } catch {
    message.error('加载知识库失败')
  } finally {
    poiLoading.value = false
  }
}

function addPoiSelected() {
  const byId = new Map(poiList.value.map((s) => [s.id, s]))
  const added = poiChecked.value
    .map((id) => byId.get(id))
    .filter(Boolean)
    .map((s) => ({ id: String(s!.id), name: s!.name, city: s!.city }))
  if (!added.length) {
    message.warning('请先勾选地点')
    return
  }
  candidates.value = [...candidates.value, ...added]
  poiDrawer.value = false
  poiChecked.value = []
  message.success(`已添加 ${added.length} 个候选`)
}

async function compute() {
  if (!origin.value) {
    message.warning('请先定位当前位置')
    return
  }
  if (!candidates.value.length) {
    message.warning('请至少添加一个候选目的地')
    return
  }
  loading.value = true
  results.value = null
  recommended.value = null
  errors.value = []
  try {
    const res: any = await computeOptimal({
      origin: origin.value,
      destinations: candidates.value,
      mode: mode.value,
      city: city.value || undefined,
    })
    const data = res?.data
    results.value = data?.results || []
    recommended.value = data?.recommended || null
    errors.value = data?.errors || []
    if (!data?.recommended) message.warning('没有可用的通勤结果，请检查候选地址')
  } catch (e: any) {
    message.error(e?.response?.data?.error || e?.message || '计算失败')
  } finally {
    loading.value = false
  }
}

function formatDuration(sec: number): string {
  if (sec <= 0) return '0 分钟'
  const totalMin = Math.ceil(sec / 60)
  if (totalMin >= 60) {
    const h = Math.floor(totalMin / 60)
    const m = totalMin % 60
    return m ? `${h} 小时 ${m} 分` : `${h} 小时`
  }
  return `${totalMin} 分钟`
}

function formatDistance(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(1)} km`
  return `${m} m`
}

function formatArrival(sec: number): string {
  const d = new Date(Date.now() + sec * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

function navUrl(item: CommuteResultItem) {
  if (item.lat == null || item.lng == null) {
    message.warning('该地点缺少坐标，无法导航')
    return
  }
  const amapMode: Record<CommuteMode, string> = {
    driving: 'car',
    transit: 'bus',
    walking: 'walk',
    cycling: 'ride',
  }
  const url =
    `https://uri.amap.com/navigation?to=${item.lng},${item.lat}` +
    `,${encodeURIComponent(item.name)}&mode=${amapMode[mode.value]}` +
    `&src=trip&coordinate=gaode&callnative=1`
  window.open(url, '_blank')
}

onMounted(detectLocation)
</script>

<template>
  <div class="commute-page">
    <header class="page-header">
      <h1>最短通勤择优</h1>
      <p class="subtitle">
        在多个候选目的地中，选出从当前位置出发通勤时间最短的那一个。
      </p>
    </header>

    <!-- 出行与起点设置 -->
    <n-card class="block" title="出行方式 / 起点">
      <n-space vertical :size="14">
        <div class="row">
          <span class="row-label">出行方式</span>
          <n-radio-group v-model:value="mode">
            <n-radio-button
              v-for="opt in modeOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </n-radio-button>
          </n-radio-group>
        </div>

        <div class="row">
          <span class="row-label">城市</span>
          <n-input
            v-model:value="city"
            placeholder="公交规划必填（如：北京）"
            style="max-width: 220px"
            clearable
          />
        </div>

        <n-divider style="margin: 4px 0" />

        <div class="row">
          <span class="row-label">起点</span>
          <n-space :size="8" align="center">
            <n-text v-if="origin" type="success">✓ {{ originName || '已定位' }}</n-text>
            <n-text v-else type="warning">未定位</n-text>
            <n-button size="small" :loading="locating" @click="detectLocation">
              重新定位
            </n-button>
            <n-button
              size="small"
              :type="pickTarget === 'origin' ? 'primary' : 'default'"
              @click="pickTarget = pickTarget === 'origin' ? null : 'origin'"
            >
              在地图选起点
            </n-button>
          </n-space>
        </div>
      </n-space>
    </n-card>

    <!-- 候选目的地 -->
    <n-card class="block" title="候选目的地">
      <n-space vertical :size="12">
        <n-space :size="8" style="max-width: 420px">
          <n-auto-complete
            v-model:value="searchName"
            :options="inputTips.map(t => ({ label: t.name, value: t.name }))"
            placeholder="输入地点名称或地址，如：三里屯 / 南昌站"
            style="flex: 1"
            clearable
            :loading="tipsLoading"
            @update:value="onSearchInput"
            @select="(val) => onSelectTip(inputTips.find(t => t.name === val)!)"
            @keyup.enter="addBySearch"
          />
          <n-button @click="addBySearch">添加</n-button>
        </n-space>

        <n-space :size="8">
          <n-button
            size="small"
            :type="pickTarget === 'destination' ? 'primary' : 'default'"
            @click="pickTarget = pickTarget === 'destination' ? null : 'destination'"
          >
            地图打点加候选
          </n-button>
          <n-button size="small" @click="openPoi">从知识库选</n-button>
        </n-space>

        <n-empty v-if="!candidates.length" description="还没有候选目的地" />
        <n-list v-else bordered>
          <n-list-item v-for="(c, i) in candidates" :key="i">
            <n-thing :title="c.name">
              <template #description>
                <n-text depth="3">
                  {{ c.lat != null && c.lng != null ? '已定位坐标' : `待地理编码${c.city ? '（' + c.city + '）' : ''}` }}
                </n-text>
              </template>
            </n-thing>
            <template #suffix>
              <n-button size="small" quaternary type="error" @click="removeCandidate(i)">
                删除
              </n-button>
            </template>
          </n-list-item>
        </n-list>
      </n-space>
    </n-card>

    <!-- 地图 -->
    <n-card class="block" title="地图">
      <n-alert
        v-if="pickTarget"
        type="info"
        :show-icon="false"
        style="margin-bottom: 8px"
      >
        点击地图{{ pickTarget === 'origin' ? '设置起点' : '添加候选点' }}（再次点击按钮取消）。
      </n-alert>
      <MapView
        :spots="mapSpots"
        :selectable="true"
        :origin-id="originSpotId"
        :routes="routePolylines"
        height="360px"
        @pick="onPick"
      />
    </n-card>

    <!-- 计算按钮 -->
    <n-button
      class="compute-btn"
      type="primary"
      size="large"
      block
      :loading="loading"
      @click="compute"
    >
      计算最短通勤
    </n-button>

    <!-- 结果 -->
    <n-card v-if="loading" class="block">
      <n-spin description="正在计算各候选通勤时间…" />
    </n-card>

    <template v-else-if="results">
      <n-alert
        v-if="errors.length"
        type="warning"
        :show-icon="true"
        style="margin-bottom: 12px"
      >
        <template v-if="hasQpsError">
          <n-space align="center" justify="space-between" :wrap="false">
            <span>部分候选触发高德接口限流（短时间内请求过多）。已成功计算的仍可使用，请稍后重试未计算的项。</span>
            <n-button size="small" :loading="loading" @click="compute">重试</n-button>
          </n-space>
        </template>
        <template v-else>
          有 {{ errors.length }} 个候选无法计算：{{ errors.map((e) => e.name).join('、') }}
        </template>
      </n-alert>

      <n-alert
        v-if="tradeoffHint"
        type="info"
        :show-icon="true"
        style="margin-bottom: 12px"
      >
        {{ tradeoffHint }}
      </n-alert>

      <n-empty v-if="!results.length" description="没有可用的通勤结果" />

      <n-card v-for="(item, idx) in results" :key="idx" class="block result-card" :class="{ recommended: item === recommended }">
        <n-space justify="space-between" align="center">
          <n-space align="center" :size="10">
            <span class="rank">#{{ idx + 1 }}</span>
            <div>
              <n-space align="center" :size="8">
                <span class="dest-name">{{ item.name }}</span>
                <n-tag v-if="item === recommended" type="primary" size="small">推荐</n-tag>
              </n-space>
              <div class="metrics">
                <n-text strong>{{ formatDuration(item.duration_sec) }}</n-text>
                <n-text depth="3"> · {{ formatDistance(item.distance_m) }}</n-text>
                <n-text v-if="mode === 'transit' && item.transfers != null" depth="3">
                  · 换乘 {{ item.transfers }} 次
                </n-text>
                <n-text v-if="item === recommended" depth="3" class="arrival">
                  · 约 {{ formatArrival(item.duration_sec) }} 到达
                </n-text>
              </div>
              <!-- 公交：地铁 / 线路信息 -->
              <div v-if="mode === 'transit' && item.transit_lines?.length" class="transit-lines">
                <n-tag
                  v-for="line in item.transit_lines"
                  :key="line"
                  :type="line.includes('地铁') ? 'primary' : 'info'"
                  size="small"
                  round
                  :bordered="false"
                  style="font-size: 11px; margin-right: 4px; opacity: 0.85"
                >
                  {{ line }}
                </n-tag>
              </div>
              <!-- 公交：逐步行程详情 -->
              <div v-if="mode === 'transit' && item.steps_detail?.length" class="transit-steps">
                <div v-for="(step, si) in item.steps_detail" :key="si" class="transit-step">
                  <span class="step-icon" :class="{ walk: step.type === 'walking' || step.type === 'transfer_walk', subway: step.type === 'subway', bus: step.type === 'bus' }">
                    {{ step.type === 'walking' || step.type === 'transfer_walk' ? '🚶' : step.type === 'subway' ? '🚇' : '🚌' }}
                  </span>
                  <span class="step-info">
                    <span class="step-label">{{ step.label }}</span>
                    <span v-if="step.departure && step.arrival" class="step-detail"> · {{ step.departure }} → {{ step.arrival }}</span>
                    <span v-else-if="step.distance_m != null" class="step-detail">{{ formatDistance(step.distance_m) }}</span>
                  </span>
                  <span class="step-time">{{ formatDuration(step.duration_sec ?? 0) }}</span>
                </div>
              </div>
              <n-text v-if="item === recommended && comparisonDiff" depth="3" class="hint">
                比次优快 {{ formatDuration(comparisonDiff) }}
              </n-text>
            </div>
          </n-space>
          <n-button size="small" @click="navUrl(item)">导航</n-button>
        </n-space>
      </n-card>
    </template>

    <!-- 知识库选择抽屉 -->
    <n-drawer v-model:show="poiDrawer" :width="360" placement="right">
      <n-drawer-content title="从知识库选择候选" closable>
        <n-spin v-if="poiLoading" />
        <n-empty v-else-if="!poiList.length" description="知识库暂无数据" />
        <n-checkbox-group v-else v-model:value="poiChecked">
          <n-space vertical :size="8">
            <n-checkbox v-for="s in poiList" :key="s.id" :value="s.id">
              {{ s.name }} · {{ s.city }}
            </n-checkbox>
          </n-space>
        </n-checkbox-group>
        <template #footer>
          <n-button type="primary" block :disabled="!poiChecked.length" @click="addPoiSelected">
            添加所选（{{ poiChecked.length }}）
          </n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<style scoped>
.commute-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}
.page-header h1 {
  font-size: 22px;
  margin: 0 0 4px;
  color: var(--text-primary, #2b2d31);
}
.subtitle {
  margin: 0 0 16px;
  color: var(--text-secondary, #6c6e74);
  font-size: 14px;
}
.block {
  margin-bottom: 16px;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.row-label {
  width: 64px;
  color: var(--text-secondary, #6c6e74);
  font-size: 14px;
  flex-shrink: 0;
}
.compute-btn {
  margin: 8px 0 20px;
}
.result-card {
  border-left: 3px solid var(--border-color, #eae5e0);
}
.result-card.recommended {
  border-left: 3px solid var(--accent, #665ca2);
  background: var(--hover-bg-active, #f3f1fa);
}
.rank {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-secondary, #999);
  width: 28px;
  text-align: center;
}
.dest-name {
  font-size: 15px;
  font-weight: 600;
}
.metrics {
  font-size: 13px;
  margin-top: 2px;
}
.arrival {
  color: var(--accent, #665ca2);
}
.hint {
  font-size: 12px;
  margin-top: 2px;
  color: var(--accent, #665ca2);
}
.transit-lines {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
}

/* 公交逐步行程时间线 */
.transit-steps {
  margin-top: 8px;
  padding: 8px 10px;
  background: var(--hover-bg, #f7f6f9);
  border-radius: 8px;
}
.transit-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  line-height: 1.8;
}
.step-icon {
  width: 22px; height: 22px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; font-size: 11px; color: #fff;
}
.step-icon.walk { background: #90a4ae; }
.step-icon.subway { background: var(--accent, #665ca2); }
.step-icon.bus { background: #42a5f5; }
.step-info { flex: 1; min-width: 0; }
.step-label { font-weight: 500; color: var(--text-primary); }
.step-detail { color: var(--text-secondary, #888); font-size: 11px; }
.step-time { color: var(--text-secondary, #999); font-size: 11px; white-space: nowrap; }
</style>
