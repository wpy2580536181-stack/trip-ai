<script setup lang="ts">
import { ref } from 'vue'
import { confirmTrip, discardTrip } from '@/api/history'

const props = defineProps<{
  newTripId: number
  parentTripId: number
  changes: {
    day: number
    period: string
    oldSpot: string
    newSpot: string
  }[]
}>()

const emit = defineEmits<{
  (e: 'confirm', tripId: number): void
  (e: 'cancel'): void
}>()

const loading = ref(false)

const periodLabels: Record<string, string> = {
  morning: '上午',
  afternoon: '下午',
  evening: '晚上',
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  accommodation: '住宿',
}

const isBudget = (period: string) => period.startsWith('预算-')

const budgetLabel = (period: string) => period.replace('预算-', '')

const handleConfirm = async () => {
  loading.value = true
  try {
    const res: any = await confirmTrip(props.newTripId)
    if (res?.code === 200) {
      emit('confirm', props.newTripId)
    }
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}

const handleCancel = async () => {
  loading.value = true
  try {
    await discardTrip(props.newTripId)
    emit('cancel')
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="diff-card">
    <div class="diff-card-header">行程修改建议</div>
    <div class="diff-card-body">
      <div v-for="(c, i) in changes" :key="i" class="diff-row">
        <template v-if="isBudget(c.period)">
          <span class="diff-day">预算</span>
          <span class="diff-period">{{ budgetLabel(c.period) }}</span>
          <span class="diff-old">{{ c.oldSpot }}</span>
          <span class="diff-arrow">→</span>
          <span class="diff-new">{{ c.newSpot }}</span>
        </template>
        <template v-else>
          <span class="diff-day">第{{ c.day }}天</span>
          <span class="diff-period">{{ periodLabels[c.period] || c.period }}</span>
          <span class="diff-old">{{ c.oldSpot }}</span>
          <span class="diff-arrow">→</span>
          <span class="diff-new">{{ c.newSpot }}</span>
        </template>
      </div>
    </div>
    <div class="diff-card-actions">
      <n-button size="small" :loading="loading" @click="handleCancel">放弃</n-button>
      <n-button size="small" type="primary" :loading="loading" @click="handleConfirm">采纳并切换</n-button>
    </div>
  </div>
</template>

<style scoped>
.diff-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
  margin: 8px 0;
  background: #fff;
}
.diff-card-header {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  background: #fafafa;
  border-bottom: 1px solid #e8e8e8;
}
.diff-card-body {
  padding: 8px 12px;
}
.diff-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 13px;
}
.diff-day {
  color: #999;
  min-width: 48px;
}
.diff-period {
  color: #999;
  min-width: 32px;
}
.diff-old {
  color: #f56c6c;
  text-decoration: line-through;
}
.diff-arrow {
  color: #ccc;
}
.diff-new {
  color: #67c23a;
  font-weight: 500;
}
.diff-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid #e8e8e8;
}
</style>
