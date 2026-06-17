<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { showToast, showConfirmDialog, showDialog } from 'vant'
import { listSpots, createSpot, updateSpot, deleteSpot, type SpotItem, type SpotInput } from '@/api/knowledge'

const items = ref<SpotItem[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 20

const totalPages = computed(() => Math.ceil(total.value / pageSize))

const filterCity = ref('')
const filterCategory = ref('')

const showForm = ref(false)
const editingId = ref<number | null>(null)
const form = ref<SpotInput>({
  name: '',
  city: '',
  category: 'attraction',
  description: '',
  tags: [],
  avgCost: undefined,
  duration: '',
  openTime: '',
  rating: undefined,
})
const tagInput = ref('')

const load = async () => {
  loading.value = true
  try {
    const res = await listSpots({
      city: filterCity.value || undefined,
      category: filterCategory.value || undefined,
      page: page.value,
      pageSize,
    })
    items.value = res.data?.items ?? []
    total.value = res.data?.total ?? 0
  } catch {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
}

const openNew = () => {
  editingId.value = null
  form.value = { name: '', city: '', category: 'attraction', description: '', tags: [] }
  tagInput.value = ''
  showForm.value = true
}

const openEdit = (spot: SpotItem) => {
  editingId.value = spot.id
  form.value = {
    name: spot.name,
    city: spot.city,
    category: spot.category,
    description: spot.description,
    tags: (spot.tags || []) as string[],
    avgCost: spot.avgCost ?? undefined,
    duration: spot.duration ?? '',
    openTime: spot.openTime ?? '',
    rating: spot.rating ?? undefined,
  }
  tagInput.value = ''
  showForm.value = true
}

const addTag = () => {
  const t = tagInput.value.trim()
  if (t && !form.value.tags?.includes(t)) {
    form.value.tags = [...(form.value.tags || []), t]
  }
  tagInput.value = ''
}

const removeTag = (idx: number) => {
  form.value.tags = form.value.tags?.filter((_, i) => i !== idx)
}

const submitForm = async () => {
  if (!form.value.name || !form.value.city || !form.value.description) {
    showToast('请填写名称、城市和描述')
    return
  }
  try {
    if (editingId.value) {
      await updateSpot(editingId.value, form.value)
      showToast('已更新')
    } else {
      await createSpot(form.value)
      showToast('已创建')
    }
    showForm.value = false
    load()
  } catch {
    showToast('操作失败')
  }
}

const confirmDelete = async (id: number) => {
  try {
    await showConfirmDialog({ title: '确认删除', message: '删除后无法恢复' })
  } catch { return }
  try {
    await deleteSpot(id)
    items.value = items.value.filter(i => i.id !== id)
    total.value--
    showToast('已删除')
  } catch {
    showToast('删除失败')
  }
}

const categoryOptions = [
  { text: '全部', value: '' },
  { text: '景点', value: 'attraction' },
  { text: '美食', value: 'food' },
  { text: '酒店', value: 'hotel' },
]

const CATEGORY_LABELS: Record<string, string> = {
  attraction: '景点',
  food: '美食',
  hotel: '酒店',
  transport: '交通',
}

onMounted(load)
</script>

<template>
  <div class="knowledge-page">
    <van-nav-bar title="知识库管理" left-arrow @click-left="$router.back()" />

    <div class="filters">
      <van-field v-model="filterCity" placeholder="筛选城市" clearable @change="page=1;load()" />
      <van-radio-group v-model="filterCategory" direction="horizontal" @change="page=1;load()" class="category-filter">
        <van-radio v-for="opt in categoryOptions" :key="opt.value" :name="opt.value">{{ opt.text }}</van-radio>
      </van-radio-group>
    </div>

    <div class="toolbar">
      <span class="total-badge">共 {{ total }} 条</span>
      <van-button type="primary" size="small" @click="openNew">新增</van-button>
    </div>

    <div class="list">
      <van-loading v-if="loading" size="24px" class="loading" />
      <van-empty v-else-if="items.length === 0" description="暂无数据，请先导入" />
      <van-cell-group v-else inset>
        <van-cell v-for="item in items" :key="item.id" @click="openEdit(item)">
          <template #title>
            <span class="spot-name">{{ item.name }}</span>
            <van-tag class="category-tag">{{ CATEGORY_LABELS[item.category] || item.category }}</van-tag>
          </template>
          <template #label>
            <span class="spot-city">{{ item.city }}</span>
            <span v-if="item.rating"> · {{ item.rating }}分</span>
          </template>
          <template #right-icon>
            <van-icon name="delete-o" @click.stop="confirmDelete(item.id)" />
          </template>
        </van-cell>
      </van-cell-group>
    </div>

    <div class="pagination" v-if="total > pageSize">
      <van-button size="small" :disabled="page <= 1" @click="page--; load()">上一页</van-button>
      <span class="page-info">第 {{ page }}/{{ totalPages }} 页，共 {{ total }} 条</span>
      <van-button size="small" :disabled="page >= totalPages" @click="page++; load()">下一页</van-button>
    </div>

    <van-dialog v-model:show="showForm" :title="editingId ? '编辑景点' : '新增景点'" show-confirm-button show-cancel-button @confirm="submitForm" @cancel="showForm=false" confirm-button-text="保存">
      <div class="form-body">
        <van-field v-model="form.name" label="名称" placeholder="必填" />
        <van-field v-model="form.city" label="城市" placeholder="必填" />
        <van-field label="分类">
          <template #input>
            <van-radio-group v-model="form.category" direction="horizontal">
              <van-radio name="attraction">景点</van-radio>
              <van-radio name="food">美食</van-radio>
              <van-radio name="hotel">酒店</van-radio>
            </van-radio-group>
          </template>
        </van-field>
        <van-field v-model="form.description" label="描述" type="textarea" rows="3" placeholder="必填" />
        <van-field v-model="form.rating" label="评分" type="digit" placeholder="0~5" />
        <van-field v-model="form.avgCost" label="均价" type="digit" placeholder="元" suffix="元" />
        <van-field v-model="form.duration" label="建议时长" placeholder="如：2-3小时" />
        <van-field v-model="form.openTime" label="开放时间" placeholder="如：08:00-18:00" />
        <van-field label="标签">
          <template #input>
            <div class="tag-editor">
              <van-tag v-for="(t, i) in form.tags" :key="i" closable @close="removeTag(i)" class="tag-item">{{ t }}</van-tag>
              <van-field v-model="tagInput" placeholder="输入标签" @keyup.enter="addTag" class="tag-input" />
            </div>
          </template>
        </van-field>
      </div>
    </van-dialog>
  </div>
</template>

<style scoped>
.knowledge-page {
  min-height: 100vh;
  background: #f7f8fa;
}
.filters {
  padding: 12px 16px 0;
  background: #fff;
}
.category-filter {
  padding: 8px 0;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
}
.total-badge {
  font-size: 13px;
  color: #999;
}
.loading {
  padding: 40px;
}
.list {
  padding: 0 0 80px;
}
.spot-name {
  font-weight: 600;
  margin-right: 8px;
}
.category-tag {
  vertical-align: middle;
}
.spot-city {
  font-size: 12px;
  color: #999;
}
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 16px;
}
.page-info {
  font-size: 13px;
  color: #666;
}
.form-body {
  padding: 16px;
  max-height: 60vh;
  overflow-y: auto;
}
.tag-editor {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.tag-item {
  margin: 2px;
}
.tag-input {
  flex: 1;
  min-width: 100px;
}
</style>
