<template>
  <div class="generating-page">
    <div class="generating-card" :class="{ finished: completed }">
      <!-- 标题 -->
      <h1 class="title">AI 正在为您规划行程</h1>
      <p class="subtitle">
        <span class="tag">{{ params.departureCity ? params.departureCity + ' → ' : '' }}{{ params.city }}</span>
        <span class="tag">{{ params.days }} 天</span>
        <span class="tag">¥{{ params.budget }}</span>
      </p>

      <!-- 总进度条：按完成步骤真实推进 -->
      <div class="total-bar">
        <div class="total-bar-fill" :style="{ width: totalPercent + '%' }"></div>
      </div>

      <!-- 步骤时间线 -->
      <ul class="steps">
        <li v-for="(step, i) in steps" :key="step.key" class="step" :class="step.status">
          <div class="step-icon">
            <span v-if="step.status === 'done'" class="check">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
                <path d="M4 12.5L9.5 18L20 6.5" stroke="white" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
            <span v-else-if="step.status === 'active'" class="spinner"></span>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <div class="step-body">
            <div class="step-name">
              {{ step.name }}
              <span v-if="step.key === 'review' && reviewRound > 1" class="retry-badge">第 {{ reviewRound }} 轮优化</span>
              <span v-if="step.status === 'done' && step.doneNote" class="step-time">{{ step.doneNote }}</span>
            </div>
            <div class="step-hint" :class="{ dots: step.status === 'active' }">{{ step.hint }}</div>
            <!-- 搜集情报的并行子项 -->
            <div v-if="step.key === 'research' && showChips" class="sub-chips">
              <span v-for="chip in chips" :key="chip.key" class="chip" :class="chip.status">{{ chip.label }}<template v-if="chip.status === 'ok'"> ✓</template></span>
            </div>
          </div>
        </li>
      </ul>

      <!-- 成功：跳转提示 -->
      <div v-if="completed" class="done-banner">行程已生成，正在跳转详情页…</div>

      <!-- 失败：重试按钮 -->
      <div v-if="error" class="result-section error-section">
        <p class="error-text">{{ error }}</p>
        <div class="action-buttons">
          <n-button type="primary" @click="startGeneration">重新生成</n-button>
          <n-button @click="goBack">返回修改</n-button>
        </div>
      </div>

      <!-- 底部：小贴士轮播 + 等待时间 + 取消 -->
      <div v-if="!error" class="gen-footer">
        <div class="fun-tip" :class="{ fade: tipFading }">{{ currentTip }}</div>
        <div class="wait-row">
          <span
            >已等待 <b class="elapsed">{{ elapsedText }}</b></span
          >
          <n-button v-if="!completed" text class="cancel-btn" @click="cancelGeneration">取消生成</n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton } from 'naive-ui'
import { fetchStream } from '../api/request'

const route = useRoute()
const router = useRouter()

// 从 query 获取参数
const params = computed(() => ({
  city: (route.query.city as string) || '',
  days: Number(route.query.days) || 3,
  budget: Number(route.query.budget) || 5000,
  departureCity: (route.query.departureCity as string) || undefined,
}))

// ---- 步骤状态 ----
type StepStatus = 'pending' | 'active' | 'done'
interface Step {
  key: string
  name: string
  hint: string
  status: StepStatus
  doneNote?: string
  startedAt?: number
}

const steps = ref<Step[]>([
  { key: 'understand', name: '理解需求', hint: '解析目的地、天数、预算与个人偏好', status: 'pending' },
  { key: 'research', name: '搜集情报', hint: '并行检索景点、美食、酒店、天气与交通数据', status: 'pending' },
  { key: 'plan', name: '规划行程', hint: '按天编排景点、餐饮与住宿，平衡预算与动线', status: 'pending' },
  { key: 'review', name: '质量审校', hint: '校验预算合理性、景点真实性与每日节奏', status: 'pending' },
  { key: 'save', name: '保存行程', hint: '生成行程详情页', status: 'pending' },
])

const chips = ref([
  { key: 'attractions', label: '景点', status: '' },
  { key: 'food', label: '美食', status: '' },
  { key: 'hotels', label: '酒店', status: '' },
  { key: 'weather', label: '天气', status: '' },
  { key: 'distance', label: '交通', status: '' },
])
const showChips = ref(false)
const reviewRound = ref(1)

const totalPercent = computed(() => {
  const done = steps.value.filter(s => s.status === 'done').length
  const activeBonus = steps.value.some(s => s.status === 'active') ? 0.5 : 0
  return Math.min(((done + activeBonus) / steps.value.length) * 100, 100)
})

const stepIndex = (key: string) => steps.value.findIndex(s => s.key === key)

const setActive = (key: string) => {
  const idx = stepIndex(key)
  if (idx === -1) return
  // 前置步骤全部补齐为完成（防事件丢失导致卡步）
  steps.value.forEach((s, i) => {
    if (i < idx && s.status !== 'done') markDone(s)
    if (i > idx) s.status = 'pending'
  })
  const step = steps.value[idx]
  if (step.status !== 'active') {
    step.status = 'active'
    step.startedAt = Date.now()
  }
}

const markDone = (step: Step, note?: string) => {
  if (step.status === 'done') return
  step.status = 'done'
  if (note) {
    step.doneNote = note
  } else if (step.startedAt) {
    step.doneNote = ((Date.now() - step.startedAt) / 1000).toFixed(1) + 's'
  }
}

const setDone = (key: string, note?: string) => {
  const idx = stepIndex(key)
  if (idx === -1) return
  steps.value.forEach((s, i) => {
    if (i <= idx) markDone(s, i === idx ? note : undefined)
  })
}

// ---- 规划阶段轮播提示 ----
const planHints = ['正在按天编排景点动线，减少折返…', '正在为每天搭配午餐与晚餐…', '正在按预算分配住宿与门票…', '正在优化游玩节奏，避免行程过满…']
let planHintTimer: ReturnType<typeof setInterval> | null = null

const startPlanHintRotation = () => {
  stopPlanHintRotation()
  let idx = 0
  planHintTimer = setInterval(() => {
    const step = steps.value[stepIndex('plan')]
    if (step?.status !== 'active') return
    idx = (idx + 1) % planHints.length
    step.hint = planHints[idx]
  }, 3500)
}
const stopPlanHintRotation = () => {
  if (planHintTimer) {
    clearInterval(planHintTimer)
    planHintTimer = null
  }
}

// ---- 小贴士轮播 ----
const funTips = [
  '行程生成后，可在详情页右侧对话框里随时调整',
  '对话里可以直接问"附近有什么好吃的"，AI 会结合行程回答',
  '不满意某个景点？点击行程卡片即可让 AI 推荐替代方案',
  '生成的行程支持多版本对比，修改后可随时切回旧版本',
]
const currentTip = ref(funTips[0])
const tipFading = ref(false)
let tipTimer: ReturnType<typeof setInterval> | null = null
let tipIdx = 0

const startTipRotation = () => {
  tipTimer = setInterval(() => {
    tipFading.value = true
    setTimeout(() => {
      tipIdx = (tipIdx + 1) % funTips.length
      currentTip.value = funTips[tipIdx]
      tipFading.value = false
    }, 400)
  }, 5000)
}
const stopTipRotation = () => {
  if (tipTimer) {
    clearInterval(tipTimer)
    tipTimer = null
  }
}

// ---- 通用状态 ----
const elapsed = ref(0)
const completed = ref(false)
const error = ref('')
let abortController: AbortController | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null
let progressReceived = false

const elapsedText = computed(() => {
  const s = elapsed.value
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}m${sec}s`
})

const stopElapsed = () => {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

// ---- 进度事件处理 ----
const onProgress = (data: any) => {
  if (!data?.stage) return
  progressReceived = true
  const { stage, status } = data
  if (stage === 'research') {
    if (status === 'start') {
      setDone('understand')
      setActive('research')
      showChips.value = true
    } else {
      // 缓存命中：chips 直接全部点亮
      if (data.cached) {
        chips.value.forEach(c => {
          c.status = 'ok'
        })
        setDone('research', '缓存命中')
      } else {
        chips.value.forEach(c => {
          if (c.status === 'loading') c.status = 'ok'
        })
        setDone('research')
      }
    }
  } else if (stage === 'plan') {
    if (status === 'start') {
      setActive('plan')
      if (data.retry) {
        const step = steps.value[stepIndex('plan')]
        step.hint = '根据审校意见调整行程中…'
        reviewRound.value = Math.max(reviewRound.value, data.attempt || 2)
      } else {
        startPlanHintRotation()
      }
    } else {
      stopPlanHintRotation()
      setDone('plan')
    }
  } else if (stage === 'review') {
    if (status === 'start') {
      setActive('review')
      if (data.attempt > 1) reviewRound.value = data.attempt
    } else if (data.passed !== false) {
      setDone('review', reviewRound.value > 1 ? `${reviewRound.value} 轮` : undefined)
    }
  } else if (stage === 'save') {
    if (status === 'start') {
      setDone('review')
      setActive('save')
    } else {
      setDone('save')
    }
  }
}

const onToolDetail = (type: string, _name: string, key?: string) => {
  if (!key) return
  const chip = chips.value.find(c => c.key === key)
  if (!chip) return
  chip.status = type === 'tool_start' ? 'loading' : 'ok'
}

// ---- 兜底：后端无 progress 事件时按时间演进（兼容旧版后端） ----
const fallbackAdvance = () => {
  if (progressReceived) return
  const s = elapsed.value
  if (s >= 2 && s < 8) {
    setDone('understand')
    setActive('research')
    showChips.value = true
  } else if (s >= 8 && s < 40) {
    setDone('research')
    setActive('plan')
  } else if (s >= 40) {
    setDone('plan')
    setActive('review')
  }
}

// ---- 生成过程 ----
const startGeneration = async () => {
  completed.value = false
  error.value = ''
  elapsed.value = 0
  progressReceived = false
  reviewRound.value = 1
  showChips.value = false
  chips.value.forEach(c => {
    c.status = ''
  })
  steps.value.forEach(s => {
    s.status = 'pending'
    s.doneNote = undefined
    s.startedAt = undefined
  })
  setActive('understand')

  elapsedTimer = setInterval(() => {
    elapsed.value++
    fallbackAdvance()
  }, 1000)
  startTipRotation()

  try {
    abortController = await fetchStream(
      'trip/recommend-stream',
      {
        city: params.value.city,
        days: params.value.days,
        budget: params.value.budget,
        departureCity: params.value.departureCity,
      },
      // onChunk — 不使用
      undefined,
      // onComplete — 行程生成完成
      (data: any) => {
        stopElapsed()
        stopPlanHintRotation()
        steps.value.forEach(s => markDone(s))
        completed.value = true

        try {
          const result = typeof data === 'string' ? JSON.parse(data) : data
          if (result.success && result.data) {
            const variants = result.data.variants
            const validVariants = (variants || []).filter((v: any) => v && v.tripId)
            setTimeout(() => {
              if (validVariants.length > 1) {
                router.push({
                  path: '/variants',
                  state: { variants: result.data },
                })
              } else if (validVariants.length === 1) {
                router.push({ path: '/detail', query: { id: validVariants[0].tripId } })
              } else {
                completed.value = false
                error.value = '行程方案全部生成失败，请重试'
              }
            }, 1200)
          } else {
            completed.value = false
            error.value = result.detail || '生成失败，请重试'
          }
        } catch {
          completed.value = false
          error.value = '结果解析失败'
        }
      },
      // onError — 生成出错
      (err: any) => {
        stopElapsed()
        stopPlanHintRotation()
        error.value = typeof err === 'string' ? err : err?.detail || '生成失败'
      },
      // onToolEvent — 兼容旧签名（详情走 onToolEventDetail）
      undefined,
      // onHeartbeat — 仅保活
      undefined,
      // onResume
      undefined,
      {
        onProgress,
        onToolEventDetail: onToolDetail,
      }
    )
  } catch (err: any) {
    if (err?.name === 'AbortError') return
    stopElapsed()
    error.value = '网络连接失败，请重试'
  }
  // 注意：fetchStream 立即返回 controller（流在后台跑），
  // 计时器在 onComplete/onError/onUnmounted 中停止，不能在此处清理
}

const cancelGeneration = () => {
  abortController?.abort()
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
  if (elapsedTimer) clearInterval(elapsedTimer)
  stopPlanHintRotation()
  stopTipRotation()
  abortController?.abort()
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
  box-shadow: 0 6px 32px rgba(0, 0, 0, 0.06);
  padding: 36px 40px 24px;
  max-width: 520px;
  width: 100%;
}

.title {
  font-size: 19px;
  font-weight: 600;
  margin: 0 0 10px;
  color: #1f2225;
  text-align: center;
}

.subtitle {
  font-size: 14px;
  color: #6b7075;
  margin: 0;
  text-align: center;
}

.tag {
  display: inline-block;
  background: #f5f6f8;
  border-radius: 4px;
  padding: 1px 8px;
  margin: 0 3px;
  font-size: 13px;
}

/* 总进度条 */
.total-bar {
  height: 6px;
  background: #eef0f2;
  border-radius: 3px;
  margin: 22px 0 26px;
  overflow: hidden;
}
.total-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #36ad6a, #18a058);
  border-radius: 3px;
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
}
.total-bar-fill::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.45), transparent);
  animation: shine 1.6s infinite;
}
.generating-card.finished .total-bar-fill::after {
  animation: none;
}
@keyframes shine {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}

/* 步骤时间线 */
.steps {
  list-style: none;
  margin: 0;
  padding: 0;
}
.step {
  display: flex;
  gap: 14px;
  position: relative;
  padding-bottom: 24px;
  text-align: left;
}
.step:last-child {
  padding-bottom: 4px;
}
.step:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 13px;
  top: 30px;
  bottom: 2px;
  width: 2px;
  background: #ececee;
  transition: background 0.4s;
}
.step.done:not(:last-child)::before {
  background: #b9e4cd;
}

.step-icon {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  border: 2px solid #ececee;
  background: #fff;
  color: #a8adb3;
  transition: all 0.35s;
  position: relative;
  z-index: 1;
}
.step.active .step-icon {
  border-color: #18a058;
  color: #18a058;
}
.step.active .step-icon::after {
  content: '';
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid rgba(24, 160, 88, 0.35);
  animation: pulse-ring 1.5s ease-out infinite;
}
@keyframes pulse-ring {
  0% {
    transform: scale(0.7);
    opacity: 1;
  }
  100% {
    transform: scale(1.25);
    opacity: 0;
  }
}
.spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(24, 160, 88, 0.25);
  border-top-color: #18a058;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.step.done .step-icon {
  background: #18a058;
  border-color: #18a058;
  color: #fff;
}
.check {
  display: flex;
  animation: pop 0.35s cubic-bezier(0.5, 1.8, 0.6, 1);
}
@keyframes pop {
  0% {
    transform: scale(0);
  }
  100% {
    transform: scale(1);
  }
}

.step-body {
  flex: 1;
  padding-top: 3px;
  min-width: 0;
}
.step-name {
  font-size: 15px;
  font-weight: 500;
  color: #a8adb3;
  transition: color 0.3s;
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.step.active .step-name {
  color: #1f2225;
  font-weight: 600;
}
.step.done .step-name {
  color: #1f2225;
}
.step-hint {
  font-size: 12.5px;
  color: #a8adb3;
  margin-top: 4px;
  min-height: 17px;
  transition: color 0.3s;
}
.step.active .step-hint {
  color: #6b7075;
}
.step-time {
  font-size: 12px;
  font-weight: 400;
  color: #18a058;
}

.dots::after {
  content: '';
  animation: dots 1.5s steps(4) infinite;
}
@keyframes dots {
  0% {
    content: '';
  }
  25% {
    content: '.';
  }
  50% {
    content: '..';
  }
  75% {
    content: '...';
  }
}

/* Research 子项 chips */
.sub-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.chip {
  font-size: 12px;
  border-radius: 20px;
  padding: 3px 10px;
  background: #f5f6f8;
  color: #a8adb3;
  transition: all 0.3s;
}
.chip.loading {
  color: #18a058;
  background: #e8f5ee;
  animation: chip-breath 1.2s ease-in-out infinite;
}
@keyframes chip-breath {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}
.chip.ok {
  color: #18a058;
  background: #e8f5ee;
  font-weight: 500;
}

/* Review 重试徽标 */
.retry-badge {
  font-size: 11px;
  color: #d09a45;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 1px 6px;
}

/* 完成横幅 */
.done-banner {
  text-align: center;
  margin-top: 16px;
  color: #18a058;
  font-size: 14px;
  font-weight: 500;
  animation: pop 0.4s;
}

/* 失败区 */
.result-section {
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
  text-align: center;
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

/* 底部 */
.gen-footer {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px dashed #ececee;
  text-align: center;
}
.fun-tip {
  font-size: 12.5px;
  color: #a8adb3;
  min-height: 18px;
  transition: opacity 0.4s;
}
.fun-tip.fade {
  opacity: 0;
}
.wait-row {
  margin-top: 10px;
  font-size: 13px;
  color: #6b7075;
  display: flex;
  justify-content: center;
  gap: 18px;
  align-items: center;
}
.elapsed {
  font-variant-numeric: tabular-nums;
}
.cancel-btn {
  color: #a8adb3;
  font-size: 13px;
}
</style>
