<template>
  <div class="budget-table">
    <div class="budget-rows">
      <div
        class="budget-row"
        v-for="(value, key) in budgetItems"
        :key="key"
      >
        <span class="budget-label">{{ getLabel(key) }}</span>
        <span class="budget-value">¥{{ value }}</span>
      </div>
    </div>
    <div class="budget-total">
      <span>总计</span>
      <span class="total-amount">¥{{ total }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: {
    type: Object,
    default: () => ({})
  },
  total: {
    type: [Number, String],
    default: 0
  }
})

const budgetItems = computed(() => {
  return {
    accommodation: props.data.accommodation || 0,
    food: props.data.food || 0,
    transportation: props.data.transportation || 0,
    tickets: props.data.tickets || 0,
    other: props.data.other || 0
  }
})

const labelMap = {
  accommodation: '住宿',
  food: '餐饮',
  transportation: '交通',
  tickets: '门票',
  other: '其他'
}

const getLabel = (key) => {
  return labelMap[key] || key
}
</script>

<style scoped>
.budget-table {
  margin-top: 8px;
}

.budget-rows {
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--border-color);
}

.budget-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  font-size: 14px;
  color: var(--text-primary);
}

.budget-row:last-child {
  border-bottom: none;
}

.budget-label {
  color: var(--text-secondary);
}

.budget-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  margin-top: 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.total-amount {
  color: var(--accent);
  font-size: 18px;
}
</style>
