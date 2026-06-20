<template>
  <div class="page-container">
    <div class="page-header">
      <van-nav-bar title="首页" />
    </div>
    <div class="page-content">
      <van-notice-bar text="基于 AI 的智能景点介绍与行程规划系统。" style="text-align: center" />
    </div>
    <div class="card search-card">
      <div class="section-title">规划您的行程</div>
      <van-field @click="showDeparturePicker = true" readonly is-link v-model="formData.departureCity" label="出发城市" placeholder="请选择出发城市" />
      <van-field @click="showCityPicker = true" readonly is-link v-model="formData.city" label="目的地" placeholder="请选择城市" />
      <van-field type="number" v-model="formData.budget" label="预算（元）" placeholder="请输入您的预算" />
      <van-field v-model="formData.days" label="天数" placeholder="请输入旅行天数" type="digit" />
      <!--确认按钮-->
      <van-button type="primary" round size="large" :loading="isloading" @click="handleSubmit">确认</van-button>
    </div>

    <div class="card quick-actions">
      <div class="section-title">快速操作</div>
      <van-grid :column-num="3" :gutter="12">
        <van-grid-item icon="chat-o" text="开始对话" @click="$router.push('/chat')" />
        <van-grid-item icon="user-o" text="个人中心" @click="$router.push('/profile')" />
        <van-grid-item icon="gold-coin-o" text="Token 用量" @click="$router.push('/token-usage')" />
      </van-grid>
    </div>
    <div class="card my-trips-entry">
      <van-cell
        title="我的行程"
        icon="records-o"
        is-link
        to="/history"
      />
    </div>
    <div class="card my-trips-entry" v-if="isAdmin">
      <van-cell
        title="知识库管理"
        icon="manager-o"
        is-link
        to="/knowledge"
      />
    </div>
    <div class="card popular-destinations">
      <div class="section-title">热门目的地</div>
      <van-grid :column-num="4" :gutter="16">
        <van-grid-item v-for="(city, index) in popularDestinations" :key="index" :text="city" @click="selectCity(city)">
          <div class="city-tag" :class="{ active: formData.city === city }">{{ city }}</div>
        </van-grid-item>
      </van-grid>
    </div>
    <van-popup v-model:show="showDeparturePicker" position="bottom" :close-on-click-modal="false">
      <van-picker title="请选择出发城市" :columns="cityColumns" @confirm="handleDepartureConfirm" @cancel="showDeparturePicker = false" />
    </van-popup>
    <van-popup v-model:show="showCityPicker" position="bottom" :close-on-click-modal="false">
      <van-picker title="请选择城市" :columns="cityColumns" @confirm="handleConfirm" @cancel="showCityPicker = false" />
    </van-popup>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed } from 'vue'
import { showToast } from 'vant'
import router from '../router'
import { ALL_CITIES, POPULAR_CITIES } from '../config/cities'

const isAdmin = computed(() => {
  const stored = typeof window !== 'undefined' ? localStorage.getItem('userInfo') : null
  if (!stored) return false
  try {
    return JSON.parse(stored).roleId === 1
  } catch {
    return false
  }
})
import { post } from '@/api/request'

interface FormData {
  departureCity: string
  city: string
  budget: string
  days: string
}

const formData = reactive<FormData>({
  departureCity: '',
  city: '',
  budget: '',
  days: '',
})
const showDeparturePicker = ref(false)
const showCityPicker = ref(false)
const allCities = ALL_CITIES
const popularDestinations = POPULAR_CITIES
// cityColumns 是一个数组，每个元素是一个对象，包含 text 和 value 属性
const cityColumns = allCities.map(item => ({
  text: item,
  value: item,
}))
// 选择城市（热门目的地）
const selectCity = (city: string) => {
  formData.city = city
}

// 处理确认选择
const handleConfirm = (result: any) => {
  formData.city = result.selectedValues[0]
  showCityPicker.value = false
}

const handleDepartureConfirm = (result: any) => {
  formData.departureCity = result.selectedValues[0]
  showDeparturePicker.value = false
}

//加载状态
const isloading = ref(false)

// 表单校验
const validateForm = () => {
  if (!formData.city) {
    showToast('请选择目的地')
    return false
  }
  if (formData.departureCity && formData.departureCity === formData.city) {
    showToast('出发城市不能与目的地相同')
    return false
  }
  if (!formData.budget || Number(formData.budget) <= 0) {
    showToast('请输入有效的预算')
    return false
  }
  if (!formData.days || Number(formData.days) < 1 || Number(formData.days) > 30) {
    showToast('请输入有效的旅行天数（1-30天）')
    return false
  }
  return true
}

// 提交表单
const handleSubmit = async () => {
  if (!validateForm()) {
    return
  }

  isloading.value = true
  try {
    const res = await post('/trip/recommend', {
      city: formData.city,
      budget: Number(formData.budget),
      days: Number(formData.days),
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
      showToast(res.error || '生成失败，请重试')
    }
  } catch (error) {
    showToast('网络错误，请稍后重试')
  } finally {
    isloading.value = false
  }
}
</script>

<style scoped>
.search-card {
  margin-bottom: 16px;
}
.city-tag {
  padding: 8px 20px;
  border-radius: 16px;
  font-size: 14px;
  color: #666;
  background-color: #f7f8fa;
  border: none;
  transition: all 0.3s ease-in-out;
  cursor: pointer;
}

.city-tag:hover {
  background-color: #e8e8e8;
  color: #333;
}

.city-tag.active {
  background-color: #1989fa;
  color: #fff;
}

:deep(.van-grid-item__content) {
  border: none !important;
  background: transparent !important;
}

:deep(.van-notice-bar__content) {
  text-align: center;
}

:deep(.van-field) {
  background-color: #f5f5f5;
  border-radius: 8px;
  margin-bottom: 12px;
}
</style>
