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

import { ref, computed, nextTick } from 'vue'
import { useMessage } from 'naive-ui'
import { NDropdown, NButton, NSpin } from 'naive-ui'
import ItineraryPrintView from './ItineraryPrintView.vue'

interface TripSlot {
  spot: string
  duration?: string
  ticket?: string
  transportation?: string
  description?: string
  imageUrl?: string
  latitude?: number
  longitude?: number
}

interface TripDay {
  day: number
  date?: string
  morning: TripSlot
  afternoon: TripSlot
  evening: TripSlot
  breakfast?: TripSlot
  lunch?: TripSlot
  dinner?: TripSlot
  accommodation?: TripSlot
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

const message = useMessage()
const loading = ref(false)
const showPrintView = ref(false)
const printWrapper = ref<HTMLElement | null>(null)

const options = [
  { label: '📷 保存为图片', key: 'image' },
  { label: '📄 导出 PDF', key: 'pdf' },
  { label: '🖨 浏览器打印', key: 'print' },
]

const disabled = computed(() => !props.tripData)

async function onSelect(key: string) {
  if (!props.tripData) {
    message.warning('请先加载行程')
    return
  }

  showPrintView.value = true
  await nextTick()
  await new Promise(r => requestAnimationFrame(r))

  const el = printWrapper.value
  if (!el) {
    message.error('导出组件未就绪')
    showPrintView.value = false
    return
  }

  const rect = el.getBoundingClientRect()
  console.log('[Export] print view dimensions:', {
    width: rect.width,
    height: rect.height,
    childCount: el.children.length,
  })
  if (rect.width < 100 || rect.height < 100) {
    console.warn('[Export] print view 尺寸异常，可能渲染失败')
  }

  const { exportAsImage, exportAsPdf, printItinerary, buildExportFilename } =
    await import('@/utils/exportItinerary')

  const filename = buildExportFilename(props.tripData.city, props.tripData.days)

  loading.value = true
  try {
    if (key === 'image') {
      await exportAsImage(el, filename)
      message.success('图片已保存')
    } else if (key === 'pdf') {
      await exportAsPdf(el, filename)
      message.success('PDF 已保存')
    } else if (key === 'print') {
      printItinerary(el, `${props.tripData.city} · ${props.tripData.days}天行程`)
    }
  } catch (e) {
    message.error('导出失败：' + ((e as Error).message || '未知错误'))
    console.error('[Export] 失败:', e)
  } finally {
    loading.value = false
    showPrintView.value = false
  }
}
</script>

<template>
  <div class="export-menu-wrapper">
    <n-dropdown
      :options="options"
      :disabled="disabled"
      @select="onSelect"
    >
      <n-button
        size="large"
        :disabled="disabled"
        style="width: 100%"
      >
        📥 导出行程
      </n-button>
    </n-dropdown>

    <div v-if="loading" class="export-overlay">
      <div class="loading-box">
        <n-spin size="large" />
        <p>正在生成，请稍候…</p>
      </div>
    </div>

    <div v-show="showPrintView" ref="printWrapper" class="print-wrapper">
      <ItineraryPrintView :trip-data="tripData" />
    </div>
  </div>
</template>

<style scoped>
.export-menu-wrapper {
  width: 100%;
}

.export-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.loading-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.loading-box p {
  margin-top: 12px;
  font-size: 14px;
}

.offscreen-wrapper,
.print-wrapper {
  position: fixed;
  top: 0;
  left: 0;
  z-index: 9998;
  pointer-events: none;
  background: #fff;
}
</style>
