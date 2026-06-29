<template>
  <div class="page-container history-page">
    <div class="history-content">
      <div class="page-header">
        <h2>我的行程</h2>
      </div>

      <div v-if="!loading && items.length === 0" class="empty-state">
        <p>还没有保存的行程，去首页生成一个吧</p>
      </div>

      <div v-else class="trip-list">
        <n-card
          v-for="t in items"
          :key="t.id"
          class="trip-card"
          size="small"
        >
          <div class="trip-card-inner">
            <div class="trip-card-body" @click="router.push({ name: 'Detail', query: { id: t.id } })">
              <div class="trip-card-title">
                {{ (t.fromCity ? t.fromCity + ' → ' : '') + t.city + ' · ' + t.days + '天' }}
              </div>
              <div class="trip-card-meta">
                {{ formatTime(t.createdAt) + ' · 预算 ' + t.budget + '元' }}
              </div>
            </div>
            <span class="delete-btn" @click.stop="onDelete(t.id)">🗑️</span>
          </div>
        </n-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { listTrips, deleteTrip, type TripListItem } from '@/api/history'

const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const items = ref<TripListItem[]>([])
const loading = ref(false)

const onDelete = (id: number) => {
  dialog.warning({
    title: '确认删除',
    content: '删除后无法恢复',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteTrip(id)
        items.value = items.value.filter(i => i.id !== id)
        message.success('已删除')
      } catch {
        message.error('删除失败')
      }
    },
  })
}

const load = async () => {
  loading.value = true
  try {
    const res = await listTrips()
    items.value = res.data?.items ?? []
  } finally {
    loading.value = false
  }
}

const formatTime = (iso: string) => {
  const d = new Date(iso)
  return `${d.getFullYear()}-${(d.getMonth() + 1).toString().padStart(2, '0')}-${d.getDate().toString().padStart(2, '0')}`
}

onMounted(load)
</script>

<style scoped>
.history-page {
  min-height: 100vh;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.history-content {
  max-width: 800px;
  margin: 0 auto;
  padding: 0 16px;
}

.page-header {
  padding: 20px 0 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.empty-state {
  text-align: center;
  padding: 80px 16px;
  color: var(--text-secondary);
}

.trip-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 60px;
}

.trip-card {
  cursor: default;
}

.trip-card-inner {
  display: flex;
  align-items: center;
  gap: 12px;
}

.trip-card-body {
  flex: 1;
  cursor: pointer;
  min-width: 0;
}

.trip-card-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.trip-card-meta {
  font-size: 13px;
  color: var(--text-secondary);
}

.delete-btn {
  font-size: 18px;
  cursor: pointer;
  opacity: 0.4;
  transition: opacity 0.15s;
  flex-shrink: 0;
  line-height: 1;
}

.delete-btn:hover {
  opacity: 1;
}
</style>
