<script setup lang="ts">
import { useRoute } from 'vue-router'
import { reactive, ref, watch } from 'vue'
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { post } from '@/api/request'
import { getTrip } from '@/api/history'

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
        <n-spin size="large" />
        <p>加载中。。。</p>
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
            <div class="day-schedule">
              <div class="schedule-section">
                <n-tag :bordered="false" color="#fa8c16" size="small">上午</n-tag>
                <spot-item :data="day.morning" />
              </div>
              <div class="schedule-section">
                <n-tag :bordered="false" color="#1890ff" size="small">下午</n-tag>
                <spot-item :data="day.afternoon" />
              </div>
              <div class="schedule-section">
                <n-tag :bordered="false" color="#52c41a" size="small">晚上</n-tag>
                <spot-item :data="day.evening" />
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

.day-schedule {
  padding: 8px 0;
}

.schedule-section {
  margin-bottom: 16px;
}

.schedule-section:last-child {
  margin-bottom: 0;
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
</style>
