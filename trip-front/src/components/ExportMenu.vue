<script setup lang="ts">
/**
 * 行程导出菜单
 *
 * 3 种导出方式:
 *  - 📷 保存为图片 (PNG)  — html-to-image
 *  - 📄 导出 PDF          — html-to-image + jsPDF
 *  - 🖨 浏览器打印        — window.print()
 *
 * 懒加载: html-to-image + jspdf 仅在用户点击导出时才 dynamic import
 */

import { ref, computed } from 'vue'
import { showToast } from 'vant'
import ItineraryPrintView from './ItineraryPrintView.vue'

interface TripSlot {
  spot: string
  duration?: string
  ticket?: string
  transportation?: string
  description?: string
}

interface TripDay {
  day: number
  date?: string
  morning: TripSlot
  afternoon: TripSlot
  evening: TripSlot
}

interface BudgetBreakdown {
  accommodation: number
  food: number
  transportation: number
  tickets: number
  other: number
}

interface TripContent {
  city: string
  days: number
  totalBudget: number
  dailyItinerary: TripDay[]
  budgetBreakdown: BudgetBreakdown
  tips: string[]
  warnings?: string[]
}

const props = defineProps<{
  tripData: TripContent | null
}>()

const showMenu = ref(false)
const loading = ref(false)
const printWrapper = ref<HTMLElement | null>(null)

const actions = [
  { name: '📷 保存为图片', key: 'image' },
  { name: '📄 导出 PDF', key: 'pdf' },
  { name: '🖨 浏览器打印', key: 'print' },
]

const disabled = computed(() => !props.tripData)

async function onSelect(action: { name: string; key: string }) {
  showMenu.value = false
  if (!props.tripData) {
    showToast('请先加载行程')
    return
  }
  const el = printWrapper.value
  if (!el) {
    showToast('导出组件未就绪')
    return
  }

  // 懒加载导出工具（html-to-image + jspdf 仅在此刻下载）
  const { exportAsImage, exportAsPdf, printItinerary, buildExportFilename } =
    await import('@/utils/exportItinerary')

  const filename = buildExportFilename(props.tripData.city, props.tripData.days)

  loading.value = true
  try {
    if (action.key === 'image') {
      await exportAsImage(el, filename)
      showToast('图片已保存')
    } else if (action.key === 'pdf') {
      await exportAsPdf(el, filename)
      showToast('PDF 已保存')
    } else if (action.key === 'print') {
      printItinerary(el, `${props.tripData.city} · ${props.tripData.days}天行程`)
    }
  } catch (e) {
    showToast('导出失败：' + ((e as Error).message || '未知错误'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="export-menu-wrapper">
    <van-button
      size="large"
      plain
      type="success"
      :disabled="disabled"
      @click="showMenu = true"
    >
      📥 导出行程
    </van-button>

    <van-action-sheet
      v-model:show="showMenu"
      :actions="actions"
      cancel-text="取消"
      close-on-click-action
      @select="onSelect"
    />

    <van-overlay :show="loading" z-index="9999">
      <div class="loading-box">
        <van-loading type="spinner" size="48px" />
        <p>正在生成，请稍候…</p>
      </div>
    </van-overlay>

    <!-- 离屏渲染：html-to-image 可捕获，用户不可见 -->
    <div ref="printWrapper" class="offscreen-wrapper">
      <ItineraryPrintView :trip-data="tripData" />
    </div>
  </div>
</template>

<style scoped>
.export-menu-wrapper {
  width: 100%;
}

.loading-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #fff;
}

.loading-box p {
  margin-top: 12px;
  font-size: 14px;
}

.offscreen-wrapper {
  position: absolute;
  left: -9999px;
  top: 0;
  z-index: -1;
  pointer-events: none;
}
</style>
