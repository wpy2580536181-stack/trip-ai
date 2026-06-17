<template>
  <div class="page-container history-page">
    <div class="page-header">
      <van-nav-bar left-arrow left-text="返回" @click-left="onBack" title="我的行程" />
    </div>
    <div class="page-body">
      <van-empty v-if="!loading && items.length === 0" description="还没有保存的行程，去首页生成一个吧" />
      <van-cell-group v-else inset>
        <van-cell
          v-for="t in items"
          :key="t.id"
          :title="(t.fromCity ? t.fromCity + ' → ' : '') + t.city + ' · ' + t.days + '天'"
          :label="formatTime(t.createdAt) + ' · 预算 ' + t.budget + '元'"
          is-link
          :to="{ name: 'Detail', query: { id: t.id } }"
        >
          <template #right-icon>
            <van-icon name="delete-o" @click.stop="onDelete(t.id)" />
          </template>
        </van-cell>
      </van-cell-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import { listTrips, deleteTrip, type TripListItem } from '@/api/history'

const router = useRouter()
const items = ref<TripListItem[]>([])
const loading = ref(false)

const onBack = () => router.back()

const onDelete = async (id: number) => {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后无法恢复' })
  } catch { return }
  try {
    await deleteTrip(id)
    items.value = items.value.filter(i => i.id !== id)
    showToast('已删除')
  } catch {
    showToast('删除失败')
  }
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
.history-page { min-height: 100vh; background: #f7f8fa; }
.page-body { padding: 12px 0 60px; }
</style>
