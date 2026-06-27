<script setup lang="ts">
import { useRoute } from 'vue-router'
import { reactive, ref, watch } from 'vue'
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { post } from '@/api/request'
import { getTrip } from '@/api/history'

const router = useRouter()
const route = useRoute()
const isloading = ref(true)
const activeDays = ref<string[]>([])

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

// 获取行程规划数据
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

  // 接口校验
  if (formData.city && formData.budget && formData.days) {
    fetchTripData()
  }
})

// 监听 ?id= 变化（optimize 后 push 到 /detail?id=newId 需要重载）
watch(
  () => route.query.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      loadTripById(Number(newId))
    }
  },
)

// 返回上一页
const onBack = () => {
  router.back()
}

// 跳转到聊天页面
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
      showToast(res.error || '优化失败')
    }
  } catch {
    showToast('网络错误')
  } finally {
    optimizing.value = false
  }
}
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <van-nav-bar
        fixed
        left-text="返回"
        left-arrow
        :title="(formData.fromCity ? formData.fromCity + ' → ' : '') + formData.city + '旅行计划'"
        @click-left="onBack"
      />
    </div>
    <div class="page-content">
      <div v-if="isloading" class="loading-container">
        <van-loading size="48px" type="spinner"/>
        加载中。。。
      </div>
      <div v-else-if="errorMsg">
        <van-empty :description="errorMsg" >
          <van-button type="primary" @click="fetchTripData">重试</van-button>
        </van-empty>
      </div>
      <template v-else-if="tripData">
        <div class ="card overview-card">
          <div class="trip-header">
            <h2>{{ formData.fromCity ? formData.fromCity + ' → ' : '' }}{{ tripData.city }} · {{ tripData.days }}天行程</h2>
            <div class="trip-budget">预算：{{ tripData.totalBudget }}元</div>
          </div>
        </div>
        <van-collapse v-model="activeDays" class="trip-collapse">
          <van-collapse-item 
          v-for="day in tripData.dailyItinerary" 
          :key="day.day" 
          :title="'第' + day.day + '天'"
          :name="day.day"
          >
          <div class="day-schedule">
            <div class="schedule-section">
              <div class="schedule-label morning">上午</div>
              <spot-item :data="day.morning" />
            </div>
            <div class="schedule-section">
              <div class="schedule-label afternoon">下午</div>
              <spot-item :data="day.afternoon" />
            </div>
            <div class="schedule-section">
              <div class="schedule-label evening">晚上</div>
              <spot-item :data="day.evening" />
            </div>
          </div>
          </van-collapse-item>
        </van-collapse>
        <div class="card budget-card">
          <div class="section-title">预算明细</div>
          <budget-table :data="tripData.budgetBreakdown" :total="tripData.totalBudget"/>
        </div>
        <div class="card tips-card" v-if="tripData">
          <div class="section-title">温馨提示</div>
          <ul class="tips-list">
            <li v-for="(tip,index) in tripData.tips" :key="index">{{ tip }}</li> 
          </ul>
        </div>
        <div class="card warnings-card" v-if="tripData">
          <div class="section-title">注意事项</div>
          <ul class="warnings-list">
            <li v-for="(warning,index) in tripData.warnings" :key="index">{{ warning }}</li> 
          </ul>
        </div>
      </template>
    </div>
    <div class="detail-footer" v-if="tripData">
      <van-button type="primary" size="large" @click="goToChat" class="primary-button">与 AI 聊天</van-button>
      <van-button v-if="currentTripMeta?.id" type="warning" size="large" :loading="optimizing" @click="onOptimize" class="optimize-button" plain>AI 优化此行程</van-button>
      <ExportMenu :trip-data="tripData" />
    </div>
  </div>
</template>


<style scoped>
.page-header{
  height: 46px;
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
  color: #323233;
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

.section-label {
  font-size: 14px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 4px;
  display: inline-block;
  margin-bottom: 8px;
}

.section-label.morning {
  background: #fff7e6;
  color: #fa8c16;
}

.section-label.afternoon {
  background: #e6f7ff;
  color: #1890ff;
}

.section-label.evening {
  background: #f6ffed;
  color: #52c41a;
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
  color: #666;
  font-size: 14px;
  border-bottom: 1px solid #f5f5f5;
}

.tips-list li:last-child,
.warnings-list li:last-child {
  border-bottom: none;
}

.detail-footer {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 12px 16px;
  background: #fff;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
  max-width: 750px;
  margin: 0 auto;
}

.error-card {
  text-align: center;
  padding: 40px 16px;
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