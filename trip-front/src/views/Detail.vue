<script setup lang="ts">
import { useRoute } from 'vue-router'
import { reactive, ref, watch } from 'vue'
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { post } from '@/api/request'
import { getTrip } from '@/api/history'
import MapView from '@/components/MapView.vue'
import type { MapSpot } from '@/components/MapView.vue'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const isloading = ref(true)
const activeDays = ref<(string | number)[]>([0])

interface TripData {
  city?: string
  budget?: number
  days?: number
  totalBudget?: number
  dailyItinerary?: any[]
  budgetBreakdown?: any
  tips?: string[]
  warnings?: string[]
}

const tripData = ref<TripData | null>(null)
const errorMsg = ref('')
const optimizing = ref(false)
const currentTripMeta = ref<{ id: number; parentTripId: number | null } | null>(null)

function getDaySpots(day: any): MapSpot[] {
  const spots: MapSpot[] = []
  for (const period of ['morning', 'afternoon', 'evening', 'breakfast', 'lunch', 'dinner', 'accommodation'] as const) {
    const slot = day[period]
    if (slot && slot.spot && slot.latitude != null && slot.longitude != null) {
      spots.push({
        name: slot.spot,
        description: slot.description,
        latitude: slot.latitude,
        longitude: slot.longitude,
      })
    }
  }
  return spots
}

const formData = reactive({
  city: '',
  budget: null as number | null,
  days: null as number | null,
  fromCity: null as string | null,
})

const fetchTripData = async () => {
  isloading.value = true
  errorMsg.value = ''
  try {
    const res = await post('/trip/recommend', {
      city: formData.city,
      budget: formData.budget,
      days: formData.days,
      departureCity: formData.fromCity || undefined,
    })
    isloading.value = false
    if (res.success && res.data) {
      tripData.value = res.data
      activeDays.value = [0]
    } else {
      errorMsg.value = res.error || '获取行程规划数据失败'
    }
  } catch (error) {
    console.error('获取行程规划数据请求失败:', error)
    errorMsg.value = '网络错误，请稍后重试'
  } finally {
    isloading.value = false
  }
}

const loadTripById = async (tripId: number) => {
  isloading.value = true
  errorMsg.value = ''
  try {
    const res = await getTrip(tripId)
    const trip = res.data
    if (trip) {
      formData.city = trip.city
      formData.budget = trip.budget
      formData.days = trip.days
      formData.fromCity = trip.fromCity ?? null
      currentTripMeta.value = { id: trip.id, parentTripId: trip.parentTripId }
      tripData.value = trip.content as TripData
      activeDays.value = [0]
    } else {
      errorMsg.value = '行程不存在'
    }
  } catch (e) {
    console.error('加载行程失败:', e)
    errorMsg.value = '加载行程失败'
  } finally {
    isloading.value = false
  }
}

onMounted(async () => {
  const tripId = route.query.id ? Number(route.query.id) : null
  if (tripId) {
    await loadTripById(tripId)
    return
  }

  formData.city = route.query.city as string || ''
  formData.budget = Number(route.query.budget) || null
  formData.days = Number(route.query.days) || null
  formData.fromCity = (route.query.departureCity as string) || null

  if (formData.city && formData.budget && formData.days) {
    fetchTripData()
  }
})

watch(
  () => route.query.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      loadTripById(Number(newId))
    }
  },
)

const onBack = () => {
  router.back()
}

const goToChat = () => {
  router.push({
    path: '/chat',
    query: {
      scene: 'detail',
      city: formData.city,
    }
  })
}

const onOptimize = async () => {
  if (!currentTripMeta.value?.id) return
  optimizing.value = true
  try {
    const res = await post('/trip/optimize', { tripId: currentTripMeta.value.id, instruction: '' })
    if (res.success && res.data) {
      const newId = (res.data as { id?: number }).id
      if (newId) {
        router.push({ path: '/detail', query: { id: newId } })
      }
    } else {
      message.error(res.error || '优化失败')
    }
  } catch {
    message.error('网络错误')
  } finally {
    optimizing.value = false
  }
}
</script>

<template>
  <div class="page-container detail-page">
    <div class="detail-content">
      <div class="page-header">
        <n-button text @click="onBack">← 返回</n-button>
        <h2 class="page-title">
          {{ (formData.fromCity ? formData.fromCity + ' → ' : '') + formData.city + '旅行计划' }}
        </h2>
      </div>

      <div v-if="isloading" class="loading-container">
        <!-- 骨架屏：行程标题 -->
        <div class="skeleton-card">
          <div class="skeleton-title skeleton-anim"></div>
          <div class="skeleton-row skeleton-anim"></div>
          <div class="skeleton-row skeleton-anim skeleton-short"></div>
        </div>

        <!-- 骨架屏：每日行程卡片 -->
        <div v-for="n in 3" :key="n" class="skeleton-card">
          <div class="skeleton-day-header skeleton-anim"></div>
          <div class="skeleton-block skeleton-anim"></div>
          <div class="skeleton-block skeleton-anim skeleton-narrow"></div>
          <div class="skeleton-block skeleton-anim"></div>
          <div class="skeleton-block skeleton-anim skeleton-narrow"></div>
        </div>

        <!-- 骨架屏：预算 + 提示 -->
        <div class="skeleton-card">
          <div class="skeleton-title skeleton-anim"></div>
          <div class="skeleton-row skeleton-anim"></div>
          <div class="skeleton-row skeleton-anim skeleton-short"></div>
        </div>
      </div>
      <div v-else-if="errorMsg" class="empty-state">
        <p>{{ errorMsg }}</p>
        <n-button type="primary" @click="fetchTripData">重试</n-button>
      </div>
      <template v-else-if="tripData">
        <div class="card overview-card">
          <div class="trip-header">
            <h2>{{ formData.fromCity ? formData.fromCity + ' → ' : '' }}{{ tripData.city }} · {{ tripData.days }}天行程</h2>
            <div class="trip-budget">预算：{{ tripData.totalBudget }}元</div>
          </div>
        </div>

        <n-collapse v-model:expanded-names="activeDays" class="trip-collapse">
          <n-collapse-item
            v-for="day in tripData.dailyItinerary"
            :key="day.day"
            :title="'第' + day.day + '天'"
            :name="day.day"
          >
            <MapView v-if="getDaySpots(day).length > 0" :spots="getDaySpots(day)" height="260px" class="day-map" />
            <div class="day-modules">
              <!-- 🏛 景点行程 -->
              <div class="module module-attractions">
                <div class="module-header">
                  <span class="module-icon">🏛</span>
                  <span class="module-title">景点行程</span>
                </div>
                <div class="period-row">
                  <n-tag :bordered="false" color="#fa8c16" size="small" class="period-tag">☀️ 上午</n-tag>
                  <spot-item :data="day.morning" />
                </div>
                <div class="period-row">
                  <n-tag :bordered="false" color="#1890ff" size="small" class="period-tag">🌤 下午</n-tag>
                  <spot-item :data="day.afternoon" />
                </div>
                <div class="period-row">
                  <n-tag :bordered="false" color="#52c41a" size="small" class="period-tag">🌙 晚上</n-tag>
                  <spot-item :data="day.evening" />
                </div>
              </div>

              <!-- 🍽 餐饮推荐 -->
              <div v-if="day.breakfast || day.lunch || day.dinner" class="module module-meals">
                <div class="module-header">
                  <span class="module-icon">🍽</span>
                  <span class="module-title">餐饮推荐</span>
                </div>
                <div class="period-row" v-if="day.breakfast">
                  <n-tag :bordered="false" color="#eb2f96" size="small" class="period-tag">🌅 早餐</n-tag>
                  <spot-item :data="day.breakfast" />
                </div>
                <div class="period-row" v-if="day.lunch">
                  <n-tag :bordered="false" color="#fa8c16" size="small" class="period-tag">☀️ 午餐</n-tag>
                  <spot-item :data="day.lunch" />
                </div>
                <div class="period-row" v-if="day.dinner">
                  <n-tag :bordered="false" color="#722ed1" size="small" class="period-tag">🌆 晚餐</n-tag>
                  <spot-item :data="day.dinner" />
                </div>
              </div>

              <!-- 🏨 住宿推荐 -->
              <div v-if="day.accommodation" class="module module-hotel">
                <div class="module-header">
                  <span class="module-icon">🏨</span>
                  <span class="module-title">住宿推荐</span>
                </div>
                <div class="period-row">
                  <spot-item :data="day.accommodation" />
                </div>
              </div>
            </div>
          </n-collapse-item>
        </n-collapse>

        <div class="card budget-card">
          <div class="section-title">预算明细</div>
          <budget-table :data="tripData.budgetBreakdown" :total="tripData.totalBudget" />
        </div>

        <div class="card tips-card" v-if="tripData">
          <div class="section-title">温馨提示</div>
          <ul class="tips-list">
            <li v-for="(tip, index) in tripData.tips" :key="index">{{ tip }}</li>
          </ul>
        </div>

        <div class="card warnings-card" v-if="tripData">
          <div class="section-title">注意事项</div>
          <ul class="warnings-list">
            <li v-for="(warning, index) in tripData.warnings" :key="index">{{ warning }}</li>
          </ul>
        </div>

        <div class="detail-footer" v-if="tripData">
          <n-button type="primary" size="large" @click="goToChat">与 AI 聊天</n-button>
          <n-button v-if="currentTripMeta?.id" type="warning" size="large" :loading="optimizing" @click="onOptimize">AI 优化此行程</n-button>
          <ExportMenu :trip-data="tripData" />
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.detail-page {
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.detail-content {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 16px;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 16px;
  gap: 16px;
  color: var(--text-secondary);
}

.empty-state {
  text-align: center;
  padding: 80px 16px;
  color: var(--text-secondary);
}

.empty-state p {
  margin-bottom: 16px;
}

.overview-card {
  margin-bottom: 16px;
}

.trip-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.trip-header h2 {
  font-size: 20px;
  color: var(--text-primary);
  margin: 0;
}

.trip-budget {
  font-size: 16px;
  color: #ee0a24;
  font-weight: 600;
}

.trip-collapse {
  margin-bottom: 16px;
}

.day-map {
  margin-bottom: 16px;
}

.day-modules {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.module {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 10px;
  overflow: hidden;
}

.module-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-color);
}

.module-icon {
  font-size: 18px;
  line-height: 1;
}

.module-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.module-attractions .module-header {
  background: rgba(250, 140, 22, 0.06);
}

.module-meals .module-header {
  background: rgba(235, 47, 150, 0.06);
}

.module-hotel .module-header {
  background: rgba(114, 46, 209, 0.06);
}

.period-row {
  padding: 6px 14px;
}

.period-tag {
  margin-bottom: 4px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-color);
}

.budget-card,
.tips-card,
.warnings-card {
  margin-bottom: 16px;
}

.tips-list,
.warnings-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.tips-list li,
.warnings-list li {
  padding: 8px 0;
  color: var(--text-secondary);
  font-size: 14px;
  border-bottom: 1px solid var(--border-color);
}

.tips-list li:last-child,
.warnings-list li:last-child {
  border-bottom: none;
}

.detail-footer {
  display: flex;
  gap: 12px;
  padding: 16px 0;
  align-items: flex-start;
}

.detail-footer > * {
  flex: 1;
  min-width: 0;
}

.card {
  background: var(--bg-primary);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

@media print {
  .page-header,
  .detail-footer {
    display: none !important;
  }
  body {
    background: white;
  }
}

/* Skeleton Screen */
.skeleton-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.skeleton-anim {
  background: linear-gradient(90deg, #f0f0f0 25%, #e8e8e8 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
  border-radius: 6px;
}

.skeleton-title {
  width: 40%;
  height: 20px;
  margin-bottom: 16px;
}

.skeleton-row {
  width: 100%;
  height: 14px;
  margin-bottom: 10px;
}

.skeleton-short {
  width: 60%;
}

.skeleton-day-header {
  width: 30%;
  height: 18px;
  margin-bottom: 14px;
}

.skeleton-block {
  width: 100%;
  height: 48px;
  margin-bottom: 10px;
}

.skeleton-narrow {
  width: 70%;
  height: 40px;
}

@keyframes skeleton-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.loading-container {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
}
</style>
