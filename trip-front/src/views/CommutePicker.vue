<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  NCard,
  NInput,
  NButton,
  NEmpty,
  NSpin,
  NAlert,
  NSpace,
  NText,
  NDivider,
  NAutoComplete,
  NTag,
  NDrawer,
  NDrawerContent,
  NCheckboxGroup,
  NCheckbox,
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
  type TransitStepDetail,
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

const modeOptions: { label: string; value: CommuteMode }[] = [
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

interface SummaryStep {
  type: 'walking' | 'subway' | 'bus'
  label: string
  duration_sec: number
}

function summarizeSteps(steps: TransitStepDetail[]): SummaryStep[] {
  const summary: SummaryStep[] = []
  let current: SummaryStep | null = null
  steps.forEach((step) => {
    const type = step.type === 'transfer_walk' ? 'walking' : step.type
    if (type !== 'walking' && type !== 'subway' && type !== 'bus') return
    if (!current || current.type !== type) {
      current = { type, label: step.label, duration_sec: step.duration_sec ?? 0 }
      summary.push(current)
    } else {
      current.duration_sec += step.duration_sec ?? 0
    }
  })
  return summary
}

function stepIcon(type: 'walking' | 'subway' | 'bus') {
  if (type === 'walking') return '🚶'
  if (type === 'subway') return '🚇'
  return '🚌'
}

function comparisonText(item: CommuteResultItem): string | null {
  if (!recommended.value || item === recommended.value) return null
  const diff = item.duration_sec - recommended.value.duration_sec
  if (diff > 0) return `慢 ${formatDuration(diff)}`
  return `快 ${formatDuration(-diff)}`
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
      <span class="brand-chip">
        <span class="brand-dot" />
        通勤工具
      </span>
      <h1>最短通勤择优</h1>
      <p class="subtitle">
        在多个候选目的地中，选出从当前位置出发通勤时间最短的那一个。
      </p>
    </header>

    <div class="commute-grid">
      <!-- 左栏：出行设置 + 候选 -->
      <div class="col col-settings">
        <!-- 出行与起点设置 -->
        <n-card class="block" title="出行方式 / 起点">
          <n-space vertical :size="14">
            <div class="row">
              <span class="row-label">出行方式</span>
              <div class="mode-segment">
                <button
                  v-for="opt in modeOptions"
                  :key="opt.value"
                  type="button"
                  class="mode-btn"
                  :class="{ active: mode === opt.value }"
                  @click="mode = opt.value"
                >
                  {{ opt.label }}
                </button>
              </div>
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
                <n-button size="small" class="btn-secondary" :loading="locating" @click="detectLocation">
                  重新定位
                </n-button>
                <n-button
                  size="small"
                  :type="pickTarget === 'origin' ? 'primary' : 'default'"
                  class="btn-secondary"
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
              <n-button type="primary" @click="addBySearch">添加</n-button>
            </n-space>

            <n-space :size="8">
              <n-button
                size="small"
                :type="pickTarget === 'destination' ? 'primary' : 'default'"
                class="btn-secondary"
                @click="pickTarget = pickTarget === 'destination' ? null : 'destination'"
              >
                地图打点加候选
              </n-button>
              <n-button size="small" class="btn-secondary" @click="openPoi">从知识库选</n-button>
            </n-space>

            <n-empty v-if="!candidates.length" description="还没有候选目的地" />
            <div v-else class="candidate-list">
              <div v-for="(c, i) in candidates" :key="i" class="candidate-item">
                <span class="candidate-marker">{{ String.fromCharCode(65 + i) }}</span>
                <div class="candidate-info">
                  <div class="candidate-name">{{ c.name }}</div>
                  <div class="candidate-meta">
                    {{ c.lat != null && c.lng != null ? '已定位坐标' : `待地理编码${c.city ? '（' + c.city + '）' : ''}` }}
                  </div>
                </div>
                <button class="candidate-delete" @click="removeCandidate(i)">删除</button>
              </div>
            </div>
          </n-space>
        </n-card>
      </div>

      <!-- 右栏：地图 + 计算 + 结果 -->
      <div class="col col-main">
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
            height="400px"
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

          <n-card
            v-for="(item, idx) in results"
            :key="idx"
            class="block result-card"
            :class="{ recommended: item === recommended }"
          >
            <div class="result-layout">
              <div class="rank-badge" :class="{ recommended: item === recommended }">
                {{ idx + 1 }}
              </div>
              <div class="result-body">
                <div class="result-title">
                  <span class="dest-name">{{ item.name }}</span>
                  <n-tag v-if="item === recommended" type="primary" size="small" round>推荐</n-tag>
                </div>
                <div class="result-metrics">
                  <span class="duration">{{ formatDuration(item.duration_sec) }}</span>
                  <span class="metric">{{ formatDistance(item.distance_m) }}</span>
                  <span v-if="mode === 'transit' && item.transfers != null" class="metric">换乘 {{ item.transfers }} 次</span>
                  <span v-if="mode === 'transit' && item.has_subway" class="metro-badge">含地铁</span>
                  <span class="metric">约 {{ formatArrival(item.duration_sec) }} 到达</span>
                </div>
                <!-- 公交：线路标签 -->
                <div v-if="mode === 'transit' && item.transit_lines?.length" class="transit-lines">
                  <n-tag
                    v-for="line in item.transit_lines"
                    :key="line"
                    :type="line.includes('地铁') ? 'primary' : 'default'"
                    size="small"
                    round
                    :bordered="false"
                    style="font-size: 11px"
                  >
                    {{ line }}
                  </n-tag>
                </div>
                <!-- 公交：横向分段明细 -->
                <div v-if="mode === 'transit' && item.steps_detail?.length" class="segment-row">
                  <template
                    v-for="(step, si) in summarizeSteps(item.steps_detail)"
                    :key="si"
                  >
                    <div class="segment" :class="step.type">
                      <span class="segment-icon">{{ stepIcon(step.type) }}</span>
                      <span class="segment-text">{{ step.label }}</span>
                      <span class="segment-time">{{ formatDuration(step.duration_sec) }}</span>
                    </div>
                    <span
                      v-if="si < summarizeSteps(item.steps_detail).length - 1"
                      class="segment-arrow"
                    >→</span>
                  </template>
                </div>
                <!-- 对比提示 -->
                <div class="comparison">
                  <span v-if="item === recommended && comparisonDiff" class="fast">
                    比次优快 {{ formatDuration(comparisonDiff) }}
                  </span>
                  <span v-else-if="comparisonText(item)" class="slow">
                    {{ comparisonText(item) }}
                  </span>
                </div>
              </div>
              <n-button size="small" class="btn-secondary nav-btn" @click="navUrl(item)">
                导航
              </n-button>
            </div>
          </n-card>
        </template>
      </div>
    </div>

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
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 28px 28px 44px;
  border-radius: 20px;
  background:
    radial-gradient(1000px 520px at 100% 0%, #EFEAFB 0%, transparent 60%),
    radial-gradient(820px 460px at 0% 100%, #EAF1FB 0%, transparent 55%),
    #F6F4EF;
}

/* 页面头部 */
.page-header {
  margin-bottom: 22px;
}
.brand-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 4px 12px;
  border-radius: 999px;
  background: rgba(102, 92, 162, 0.1);
  color: var(--accent, #665ca2);
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 10px;
}
.brand-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent, #665ca2);
}
.page-header h1 {
  font-size: 26px;
  margin: 0 0 6px;
  color: var(--text-primary, #2b2d31);
}
.subtitle {
  margin: 0;
  color: var(--text-secondary, #6c6e74);
  font-size: 14px;
}

/* 桌面双栏网格；窄屏退化为单列 */
.commute-grid {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 20px;
  align-items: start;
}
.col {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
@media (max-width: 960px) {
  .commute-grid {
    grid-template-columns: 1fr;
  }
  .commute-page {
    padding: 20px 16px 32px;
  }
}

/* 品牌卡片：圆角 20px + 描边 + 阴影，覆盖 Naive 默认 */
.commute-page :deep(.n-card) {
  border-radius: 20px;
  border: 1px solid #ECE7F2;
  box-shadow: 0 24px 60px -28px rgba(40, 32, 80, 0.35);
  background: #ffffff;
}
.commute-page :deep(.n-card__content) {
  padding: 20px;
}

.block {
  margin: 0;
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

/* 出行方式分段选择器 */
.mode-segment {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: #F6F5F9;
  border: 1px solid #E4E1ED;
  border-radius: 12px;
}
.mode-btn {
  padding: 7px 18px;
  border: none;
  border-radius: 10px;
  background: transparent;
  color: #6C6E74;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.mode-btn:hover {
  color: #2B2D31;
}
.mode-btn.active {
  background: #665CA2;
  color: #fff;
  font-weight: 600;
}

/* 次要按钮：白底 + 紫字/紫边框 */
.commute-page :deep(.n-button.btn-secondary) {
  background: #ffffff;
  border: 1px solid #E4E1ED;
  color: #665CA2;
}
.commute-page :deep(.n-button.btn-secondary:not(.n-button--disabled):hover) {
  background: #F4F1FB;
  border-color: #665CA2;
}
.commute-page :deep(.n-button.btn-secondary.n-button--primary-type) {
  background: #665CA2;
  border-color: #665CA2;
  color: #fff;
}

.compute-btn {
  margin: 0 0 4px;
}

/* 候选列表 */
.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.candidate-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: #F6F5F9;
  border: 1px solid #E4E1ED;
  border-radius: 12px;
  transition: all 0.2s;
}
.candidate-item:hover {
  background: #F4F1FB;
  border-color: #DCD7EA;
}
.candidate-marker {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ECE7F2;
  color: #6C6E74;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.candidate-info {
  flex: 1;
  min-width: 0;
}
.candidate-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #2b2d31);
}
.candidate-meta {
  font-size: 12px;
  color: var(--text-secondary, #6c6e74);
  margin-top: 2px;
}
.candidate-delete {
  padding: 4px 10px;
  border: 1px solid #E4E1ED;
  border-radius: 8px;
  background: #fff;
  color: #665CA2;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.candidate-delete:hover {
  background: #F4F1FB;
  border-color: #665CA2;
}

/* 结果卡片 */
.result-card {
  border-left: 4px solid var(--border-color, #eae5e0);
}
.result-card.recommended {
  border-left: 4px solid var(--accent, #665ca2);
  background: #F4F1FB;
}
.result-layout {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.rank-badge {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ECE7F2;
  color: #6C6E74;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}
.rank-badge.recommended {
  background: #665CA2;
  color: #fff;
}
.result-body {
  flex: 1;
  min-width: 0;
}
.result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.result-metrics {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 12px;
  font-size: 13px;
  color: var(--text-secondary, #6c6e74);
}
.result-metrics .duration {
  color: var(--text-primary, #2b2d31);
  font-weight: 700;
  font-size: 15px;
}
.metro-badge {
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(102, 92, 162, 0.1);
  color: #665CA2;
  font-size: 11px;
  font-weight: 600;
}
.transit-lines {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.segment-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  padding: 10px 12px;
  background: #F7F6F9;
  border-radius: 10px;
}
.segment {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #E4E1ED;
  font-size: 12px;
  color: var(--text-primary, #2b2d31);
}
.segment.walk { border-color: #90a4ae; }
.segment.subway { border-color: #665CA2; background: #F4F1FB; }
.segment.bus { border-color: #42a5f5; }
.segment-icon {
  font-size: 13px;
}
.segment-text {
  font-weight: 500;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.segment-time {
  color: var(--text-secondary, #6c6e74);
  font-size: 11px;
}
.segment-arrow {
  color: #C6C2D0;
  font-size: 12px;
  font-weight: 700;
}
.comparison {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 500;
}
.comparison .fast { color: #3FA66A; }
.comparison .slow { color: #6C6E74; }
.nav-btn {
  flex-shrink: 0;
}
</style>
