<template>
  <van-popup
    :show="show"
    position="left"
    :style="{ width: '80%', maxWidth: '320px', height: '100%' }"
    @update:show="(v: boolean) => emit('update:show', v)"
  >
    <div class="drawer">
      <div class="drawer-header">
        <van-button type="primary" block @click="onNew">新建对话</van-button>
      </div>
      <div class="drawer-body">
        <van-empty v-if="!loading && items.length === 0" description="暂无历史对话" />
        <van-cell-group v-else inset>
          <van-cell
            v-for="item in items"
            :key="item.id"
            :title="item.title || '新对话'"
            :label="formatTime(item.updatedAt)"
            is-link
            @click="onSelect(item.id)"
          >
            <template #right-icon>
              <van-icon name="cross" @click.stop="onDelete(item.id)" />
            </template>
          </van-cell>
        </van-cell-group>
      </div>
    </div>
  </van-popup>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { showConfirmDialog, showToast } from 'vant'
import { listConversations, deleteConversation, type ConversationListItem } from '@/api/conversation'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{
  'update:show': [v: boolean]
  select: [id: number]
  new: []
}>()

const items = ref<ConversationListItem[]>([])
const loading = ref(false)

const load = async () => {
  loading.value = true
  try {
    const res = await listConversations()
    items.value = res.data?.items ?? []
  } catch (e) {
    showToast('加载历史对话失败')
  } finally {
    loading.value = false
  }
}

watch(() => props.show, (v) => { if (v) load() })

const onSelect = (id: number) => {
  emit('select', id)
  emit('update:show', false)
}

const onNew = () => {
  emit('new')
  emit('update:show', false)
}

const onDelete = async (id: number) => {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后无法恢复' })
  } catch { return }
  try {
    await deleteConversation(id)
    items.value = items.value.filter(i => i.id !== id)
    showToast('已删除')
  } catch (e) {
    showToast('删除失败')
  }
}

const formatTime = (iso: string) => {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}
</script>

<style scoped>
.drawer { display: flex; flex-direction: column; height: 100%; background: #fff; }
.drawer-header { padding: 16px; border-bottom: 1px solid #f0f0f0; }
.drawer-body { flex: 1; overflow-y: auto; padding: 12px 0; }
</style>
