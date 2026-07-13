<template>
  <div class="generating-page">
    <div class="generating-card">
      <!-- 标题 -->
      <h1 class="title">🤖 AI 正在为您规划行程</h1>
      <p class="subtitle">{{ params.city }} · {{ params.days }}天 · ¥{{ params.budget }}</p>

      <!-- 进度动画 -->
      <div class="progress-section">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
        </div>
        <p class="status-text">{{ statusText }}</p>
      </div>

      <!-- 耗时显示 -->
      <div class="time-info">
        <span class="time-label">已等待</span>
        <span class="time-value">{{ elapsedText }}</span>
      </div>

      <!-- 成功：跳转提示 -->
      <div v-if="completed" class="result-section">
        <div class="success-icon">✅</div>
        <p class="success-text">行程生成完成！正在跳转...</p>
      </div>

      <!-- 失败：重试按钮 -->
      <div v-if="error" class="result-section error-section">
        <div class="error-icon">❌</div>
        <p class="error-text">{{ error }}</p>
        <div class="action-buttons">
          <n-button type="primary" @click="startGeneration">重新生成</n-button>
          <n-button @click="goBack">返回修改</n-button>
        </div>
      </div>

      <!-- 取消按钮 -->
      <n-button v-if="!completed && !error" text class="cancel-btn" @click="cancelGeneration">
        取消生成
      </n-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, useMessage } from 'naive-ui'
import { fetchStream } from '../api/request'

const route = useRoute()
const router = useRouter()
const message = useMessage()

// 从 query 获取参数
const params = computed(() => ({
  city: route.query.city as string || '',
  days: Number(route.query.days) || 3,
  budget: Number(route.query.budget) || 5000,
  departureCity: route.query.departureCity as string || undefined,
}))

// 状态
const progressPercent = ref(0)
const statusText = ref('正在连接服务器...')
const elapsed = ref(0)
const completed = ref(false)
const error = ref('')
let abortController: AbortController | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null

// 耗时显示
const elapsedText = computed(() => {
  const s = elapsed.value
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}m${sec}s`
})

// 生成过程
const startGeneration = async () => {
  completed.value = false
  error.value = ''
  progressPercent.value = 10
  statusText.value = '正在连接服务器...'
  elapsed.value = 0
  elapsedTimer = setInterval(() => { elapsed.value++ }, 1000)

  try {
    abortController = await fetchStream(
      '/api/trip/recommend-stream',
      {
        city: params.value.city,
        days: params.value.days,
        budget: params.value.budget,
        departureCity: params.value.departureCity,
      },
      // onChunk — 用于流式增量数据（当前 /recommend-stream 不使用）
      undefined,
      // onComplete — 行程生成完成
      (data: string) => {
        progressPercent.value = 100
        statusText.value = '行程生成完成！'
        completed.value = true

        try {
          const result = typeof data === 'string' ? JSON.parse(data) : data
          if (result.success && result.data) {
            const tripId = result.data.id
            if (tripId) {
              setTimeout(() => {
                router.push({ path: '/detail', query: { id: tripId } })
              }, 1500)
            } else {
              setTimeout(() => {
                router.push({
                  path: '/detail',
                  query: {
                    city: params.value.city,
                    budget: params.value.budget,
                    days: params.value.days,
                  },
                })
              }, 1500)
            }
          } else {
            error.value = result.detail || '生成失败，请重试'
          }
        } catch {
          error.value = '结果解析失败'
        }
      },
      // onError — 生成出错
      (err: any) => {
        error.value = (typeof err === 'string') ? err : (err?.detail || '生成失败')
        progressPercent.value = 0
      },
      // onToolEvent — 工具调用事件
      (type: string, name: string) => {
        if (type === 'tool_start') {
          progressPercent.value = 20
          statusText.value = '正在收集信息...'
        }
      },
      // onHeartbeat — 心跳保活
      () => {
        const base = 20
        const maxProgress = 80
        const heartbeatProgress = Math.min(elapsed.value * 2, maxProgress)
        progressPercent.value = base + heartbeatProgress
        statusText.value = `AI 正在思考中...（已处理 ${elapsed.value}s）`
      },
    )
  } catch (err: any) {
    if (err?.name === 'AbortError') {
      statusText.value = '已取消'
      return
    }
    error.value = '网络连接失败，请重试'
    progressPercent.value = 0
  } finally {
    if (elapsedTimer) {
      clearInterval(elapsedTimer)
      elapsedTimer = null
    }
  }
}

const cancelGeneration = () => {
  if (abortController) {
    abortController.abort()
  }
  router.push('/')
}

const goBack = () => {
  router.push('/')
}

onMounted(() => {
  if (params.value.city) {
    startGeneration()
  } else {
    error.value = '缺少行程参数，请重新填写'
  }
})

onUnmounted(() => {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
  }
  if (abortController) {
    abortController.abort()
  }
})
</script>

<style scoped>
.generating-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 70vh;
  padding: 24px;
}

.generating-card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  padding: 48px 40px;
  text-align: center;
  max-width: 480px;
  width: 100%;
}

.title {
  font-size: 22px;
  font-weight: 600;
  margin: 0 0 8px;
  color: #333;
}

.subtitle {
  font-size: 14px;
  color: #888;
  margin: 0 0 36px;
}

.progress-section {
  margin-bottom: 24px;
}

.progress-bar {
  height: 8px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 12px;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #18a058, #36ad6a);
  border-radius: 4px;
  transition: width 0.5s ease;
}

.status-text {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.time-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
}

.time-label {
  font-size: 13px;
  color: #999;
}

.time-value {
  font-size: 20px;
  font-weight: 500;
  color: #333;
  font-variant-numeric: tabular-nums;
}

.result-section {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #f0f0f0;
}

.success-icon,
.error-icon {
  font-size: 36px;
  margin-bottom: 12px;
}

.success-text {
  font-size: 15px;
  color: #18a058;
  margin: 0;
}

.error-text {
  font-size: 14px;
  color: #d03050;
  margin: 0 0 16px;
}

.action-buttons {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.cancel-btn {
  margin-top: 16px;
  color: #999;
}
</style>
