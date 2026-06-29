<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { ALL_CITIES, POPULAR_CITIES } from '../config/cities'
import { post } from '@/api/request'

const router = useRouter()
const message = useMessage()

const isAdmin = computed(() => {
  const stored = typeof window !== 'undefined' ? localStorage.getItem('userInfo') : null
  if (!stored) return false
  try {
    return JSON.parse(stored).roleId === 1
  } catch {
    return false
  }
})

interface FormData {
  departureCity: string
  city: string
  budget: number | null
  days: number | null
}

const formData = reactive<FormData>({
  departureCity: '',
  city: '',
  budget: null,
  days: null,
})

const cityOptions = ALL_CITIES.map(c => ({ label: c, value: c }))
const popularDestinations = POPULAR_CITIES
const isloading = ref(false)

const selectCity = (city: string) => {
  formData.city = city
}

const validateForm = () => {
  if (!formData.city) {
    message.warning('请选择目的地')
    return false
  }
  if (formData.departureCity && formData.departureCity === formData.city) {
    message.warning('出发城市不能与目的地相同')
    return false
  }
  if (!formData.budget || formData.budget <= 0) {
    message.warning('请输入有效的预算')
    return false
  }
  if (!formData.days || formData.days < 1 || formData.days > 30) {
    message.warning('请输入有效的旅行天数（1-30天）')
    return false
  }
  return true
}

const handleSubmit = async () => {
  if (!validateForm()) return
  isloading.value = true
  try {
    const res = await post('/trip/recommend', {
      city: formData.city,
      budget: formData.budget,
      days: formData.days,
      departureCity: formData.departureCity || undefined,
    })
    if (res.success && res.data) {
      const tripId = (res.data as { id?: number }).id
      if (tripId) {
        router.push({ path: '/detail', query: { id: tripId } })
      } else {
        router.push({
          path: '/detail',
          query: {
            city: formData.city,
            budget: formData.budget,
            days: formData.days,
            departureCity: formData.departureCity || undefined,
          },
        })
      }
    } else {
      message.error(res.error || '生成失败，请重试')
    }
  } catch {
    message.error('网络错误，请稍后重试')
  } finally {
    isloading.value = false
  }
}
</script>

<template>
  <div class="home-page">
    <div class="home-header">
      <h1>规划您的旅程</h1>
      <p class="home-subtitle">AI 帮你定制完美行程</p>
    </div>

    <div class="card search-card">
      <div class="section-title">行程信息</div>
      <n-form :model="formData">
        <n-form-item label="出发城市" path="departureCity">
          <n-select
            v-model:value="formData.departureCity"
            :options="cityOptions"
            placeholder="请选择出发城市（可选）"
            filterable
            clearable
          />
        </n-form-item>
        <n-form-item label="目的地" path="city">
          <n-select
            v-model:value="formData.city"
            :options="cityOptions"
            placeholder="请选择目的地"
            filterable
          />
        </n-form-item>
        <n-form-item label="预算（元）" path="budget">
          <n-input-number v-model:value="formData.budget" placeholder="请输入预算" :min="1" style="width: 100%" />
        </n-form-item>
        <n-form-item label="天数" path="days">
          <n-input-number v-model:value="formData.days" placeholder="请输入旅行天数（1-30天）" :min="1" :max="30" style="width: 100%" />
        </n-form-item>
      </n-form>
      <n-button type="primary" block strong :loading="isloading" @click="handleSubmit" size="large">
        生成行程
      </n-button>
    </div>

    <div class="card quick-actions-card">
      <div class="section-title">快速操作</div>
      <div class="action-grid">
        <div class="action-card" @click="router.push('/chat')">
          <div class="action-icon">💬</div>
          <div class="action-label">开始对话</div>
        </div>
        <div class="action-card" @click="router.push('/profile')">
          <div class="action-icon">👤</div>
          <div class="action-label">个人中心</div>
        </div>
        <div class="action-card" @click="router.push('/token-usage')">
          <div class="action-icon">📊</div>
          <div class="action-label">Token 用量</div>
        </div>
        <div v-if="isAdmin" class="action-card" @click="router.push('/admin/feedback')">
          <div class="action-icon">📝</div>
          <div class="action-label">反馈 Dashboard</div>
        </div>
      </div>
    </div>

    <div class="card link-entry-card">
      <div class="link-entry" @click="router.push('/history')">
        <span>📋 我的行程</span>
        <span class="link-arrow">→</span>
      </div>
      <div v-if="isAdmin" class="link-entry" @click="router.push('/knowledge')">
        <span>📚 知识库管理</span>
        <span class="link-arrow">→</span>
      </div>
    </div>

    <div class="card popular-card">
      <div class="section-title">热门目的地</div>
      <div class="destination-grid">
        <div
          v-for="city in popularDestinations"
          :key="city"
          class="city-tag"
          :class="{ active: formData.city === city }"
          @click="selectCity(city)"
        >
          {{ city }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  width: 100%;
}

.home-header {
  margin-bottom: 28px;
}

.home-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary, #2B2D31);
  margin: 0 0 8px 0;
  line-height: 1.2;
}

.home-subtitle {
  font-size: 15px;
  color: var(--text-secondary, #6C6E74);
  margin: 0;
}

.card {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 16px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary, #2B2D31);
  margin-bottom: 16px;
}

.search-card :deep(.n-form-item) {
  margin-bottom: 4px;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.action-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 8px;
  border: 1px solid var(--border-color, #EAE5E0);
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}

.action-card:hover {
  background: var(--hover-bg);
}

.action-icon {
  font-size: 24px;
  line-height: 1;
}

.action-label {
  font-size: 13px;
  color: var(--text-secondary, #6C6E74);
  white-space: nowrap;
}

.link-entry-card {
  padding: 0;
}

.link-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-primary, #2B2D31);
  transition: background 0.15s;
}

.link-entry:hover {
  background: var(--hover-bg);
}

.link-entry + .link-entry {
  border-top: 1px solid var(--border-color, #EAE5E0);
}

.link-arrow {
  color: var(--text-secondary, #6C6E74);
  font-size: 16px;
}

.destination-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 10px;
}

.city-tag {
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 14px;
  color: var(--text-secondary, #6C6E74);
  background: transparent;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
}

.city-tag:hover {
  background: var(--hover-bg);
  color: var(--text-primary, #2B2D31);
}

.city-tag.active {
  background: var(--accent, #665CA2);
  color: #fff;
}
</style>
