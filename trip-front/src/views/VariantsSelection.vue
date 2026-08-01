<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'

const router = useRouter()
const route = useRoute()
const message = useMessage()

interface VariantSummary {
  variantType: string
  tripId: number
  summary: {
    spotCount: number
    highlights: string[]
    budget?: number
  }
}

interface VariantsData {
  id?: number
  variants?: VariantSummary[]
  city?: string
  [key: string]: any
}

const variants = ref<VariantSummary[]>([])
const city = ref('')
const selectedVariant = ref<number | null>(null)

const variantLabels: Record<string, { label: string; color: string; desc: string }> = {
  economy: {
    label: '经济实惠',
    color: '#18a058',
    desc: '性价比优先，精选免费景点与平价餐饮',
  },
  comfort: {
    label: '舒适标准',
    color: '#2080f0',
    desc: '均衡体验，兼顾品质与价格',
  },
  photo: {
    label: '拍照打卡',
    color: '#d03050',
    desc: '网红景点与最佳拍照角度',
  },
}

const loadVariants = () => {
  try {
    const data = (route as any).state as VariantsData | undefined
    if (data?.variants && Array.isArray(data.variants) && data.variants.length > 0) {
      variants.value = data.variants
      city.value = data.city || ''
      return
    }
  } catch { /* ignore */ }
  message.error('未找到行程方案，请重新生成')
  router.replace('/')
}

const selectVariant = (idx: number) => {
  const v = variants.value[idx]
  if (!v) return
  router.push({
    path: '/detail',
    query: { id: String(v.tripId) },
  })
}

const goBack = () => {
  router.push('/')
}

onMounted(() => {
  loadVariants()
})
</script>

<template>
  <div class="variants-page">
    <div class="variants-container">
      <div class="page-header">
        <h2 class="page-title">为你生成了 3 套方案</h2>
        <p class="page-subtitle">
          {{ city ? `${city} · ` : '' }}点击卡片查看详情并确认行程
        </p>
      </div>

      <div v-if="variants.length === 0" class="empty-state">
        <p>加载中...</p>
      </div>

      <div v-else class="variants-grid">
        <div
          v-for="(variant, idx) in variants"
          :key="variant.variantType || idx"
          class="variant-card"
          :class="{ selected: selectedVariant === idx }"
          @click="selectVariant(idx)"
        >
          <div class="card-header">
            <div class="variant-icon" :style="{ background: variantLabels[variant.variantType]?.color || '#666' }">
              {{ (variantLabels[variant.variantType]?.label || variant.variantType)?.charAt(0) }}
            </div>
            <div class="variant-type">
              <h3 class="variant-title">{{ variantLabels[variant.variantType]?.label || variant.variantType }}</h3>
              <p class="variant-desc">{{ variantLabels[variant.variantType]?.desc || '' }}</p>
            </div>
            <div class="variant-badge">
              <span class="badge-number">{{ idx + 1 }}</span>
            </div>
          </div>

          <div class="card-body">
            <div class="stat-row">
              <div class="stat-item">
                <span class="stat-value">{{ variant.summary?.spotCount || 0 }}</span>
                <span class="stat-label">个景点</span>
              </div>
              <div class="stat-item" v-if="variant.summary?.budget">
                <span class="stat-value">¥{{ variant.summary.budget.toLocaleString() }}</span>
                <span class="stat-label">预算</span>
              </div>
            </div>

            <div class="highlights" v-if="variant.summary?.highlights?.length">
              <p class="highlights-title">亮点</p>
              <div class="highlights-list">
                <span
                  v-for="(hl, i) in variant.summary.highlights.slice(0, 4)"
                  :key="i"
                  class="highlight-tag"
                >
                  {{ hl }}
                </span>
              </div>
            </div>
          </div>

          <div class="card-footer">
            <button class="select-btn" :style="{ background: variantLabels[variant.variantType]?.color || '#666' }">
              查看详情
            </button>
          </div>
        </div>
      </div>

      <div class="back-row">
        <button class="back-btn" @click="goBack">返回重新规划</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.variants-page {
  min-height: 100vh;
  background: #f7f8fa;
  padding: 32px 16px;
}
.variants-container {
  max-width: 1100px;
  margin: 0 auto;
}
.page-header {
  text-align: center;
  margin-bottom: 32px;
}
.page-title {
  font-size: 22px;
  font-weight: 600;
  color: #1f2225;
  margin: 0 0 8px;
}
.page-subtitle {
  font-size: 14px;
  color: #6b7075;
  margin: 0;
}
.variants-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 20px;
}
.variant-card {
  background: #fff;
  border-radius: 14px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  padding: 20px;
  cursor: pointer;
  transition: transform .2s, box-shadow .2s;
  border: 2px solid transparent;
}
.variant-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.1);
  border-color: #18a058;
}
.variant-card.selected {
  border-color: #18a058;
  box-shadow: 0 6px 20px rgba(24, 160, 88, .2);
}
.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.variant-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
  flex-shrink: 0;
}
.variant-type { flex: 1; }
.variant-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2225;
  margin: 0 0 3px;
}
.variant-desc {
  font-size: 12.5px;
  color: #6b7075;
  margin: 0;
}
.variant-badge {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  color: #666;
  flex-shrink: 0;
}
.card-body {
  padding: 12px 0;
  border-top: 1px dashed #eee;
  border-bottom: 1px dashed #eee;
  margin-bottom: 14px;
}
.stat-row {
  display: flex;
  gap: 20px;
  margin-bottom: 10px;
}
.stat-item { display: flex; flex-direction: column; }
.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: #1f2225;
  font-variant-numeric: tabular-nums;
}
.stat-label {
  font-size: 12px;
  color: #a8adb3;
  margin-top: 2px;
}
.highlights-title {
  font-size: 12px;
  color: #6b7075;
  margin: 0 0 6px;
}
.highlights-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.highlight-tag {
  font-size: 12px;
  color: #18a058;
  background: #e8f5ee;
  border-radius: 20px;
  padding: 2px 10px;
}
.card-footer { text-align: right; }
.select-btn {
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 22px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity .2s;
}
.select-btn:hover { opacity: .85; }
.back-row {
  text-align: center;
  margin-top: 28px;
}
.back-btn {
  background: transparent;
  color: #a8adb3;
  border: none;
  font-size: 13px;
  cursor: pointer;
}
.back-btn:hover { color: #1f2225; }
</style>
