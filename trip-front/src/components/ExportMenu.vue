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
const showPrintView = ref(false)
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

  // 关键：临时显示 print view 让 html-to-image 抓到正确尺寸
  // (position: absolute + left: -9999px 在部分浏览器返回 0 尺寸)
  showPrintView.value = true
  await nextTick()
  // 再等一帧确保浏览器完成布局
  await new Promise(r => requestAnimationFrame(r))

  const el = printWrapper.value
  if (!el) {
    showToast('导出组件未就绪')
    showPrintView.value = false
    return
  }

  // 诊断日志：导出前打印实际尺寸（如果还是 0 就能立刻看出问题）
  const rect = el.getBoundingClientRect()
  console.log('[Export] print view dimensions:', {
    width: rect.width,
    height: rect.height,
    childCount: el.children.length,
  })
  if (rect.width < 100 || rect.height < 100) {
    console.warn('[Export] print view 尺寸异常，可能渲染失败')
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
    console.error('[Export] 失败:', e)
  } finally {
    loading.value = false
    showPrintView.value = false
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

    <!-- 临时显示：导出时显示让 html-to-image 抓到正确尺寸 -->
    <div v-show="showPrintView" ref="printWrapper" class="print-wrapper">
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

.offscreen-wrapper,
.print-wrapper {
  /* 导出时短暂显示在 viewport 左上角（被 van-overlay 遮挡用户不可见），
     让 html-to-image 抓到正确尺寸后立刻隐藏。
     不用 opacity:0 避免 html-to-image 抓到透明背景 */
  position: fixed;
  top: 0;
  left: 0;
  z-index: 9998;
  pointer-events: none;
  background: #fff;
}
</style>
