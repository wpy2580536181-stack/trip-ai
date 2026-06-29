<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { useMessage, useDialog, NButton, type DataTableColumn } from 'naive-ui'
import { listSpots, createSpot, updateSpot, deleteSpot, type SpotItem, type SpotInput } from '@/api/knowledge'

const message = useMessage()
const dialog = useDialog()

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
const jumpPage = ref('')

const jumpToPage = () => {
  const p = Number(jumpPage.value)
  if (p >= 1 && p <= totalPages.value && p !== page.value) {
    page.value = p
    load()
  }
  jumpPage.value = ''
}

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
    message.error('加载失败')
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
    message.warning('请填写名称、城市和描述')
    return
  }
  try {
    if (editingId.value) {
      await updateSpot(editingId.value, form.value)
      message.success('已更新')
    } else {
      await createSpot(form.value)
      message.success('已创建')
    }
    showForm.value = false
    load()
  } catch {
    message.error('操作失败')
  }
}

const confirmDelete = (id: number) => {
  dialog.warning({
    title: '确认删除',
    content: '删除后无法恢复',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteSpot(id)
        items.value = items.value.filter(i => i.id !== id)
        total.value--
        message.success('已删除')
      } catch {
        message.error('删除失败')
      }
    },
  })
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

const columns: DataTableColumn[] = [
  { title: '名称', key: 'name', ellipsis: { tooltip: true } },
  { title: '城市', key: 'city', width: 100 },
  {
    title: '分类',
    key: 'category',
    width: 80,
    render: (row: SpotItem) => CATEGORY_LABELS[row.category] || row.category,
  },
  {
    title: '评分',
    key: 'rating',
    width: 80,
    render: (row: SpotItem) => row.rating ? `${row.rating}分` : '-',
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: (row: SpotItem) =>
      h('div', { style: 'display: flex; gap: 8px;' }, [
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => openEdit(row) }, { default: () => '编辑' }),
        h(NButton, { size: 'tiny', quaternary: true, type: 'error', onClick: () => confirmDelete(row.id) }, { default: () => '删除' }),
      ]),
  },
]

onMounted(load)
</script>

<template>
  <div class="knowledge-page">
    <h2 class="page-title">知识库管理</h2>

    <div class="filters">
      <div class="filter-row">
        <n-input v-model:value="filterCity" placeholder="筛选城市" clearable @update:value="page=1;load()" style="width: 200px" />
        <n-radio-group v-model:value="filterCategory" @update:value="page=1;load()">
          <n-radio v-for="opt in categoryOptions" :key="opt.value" :value="opt.value" :label="opt.text" />
        </n-radio-group>
      </div>
    </div>

    <div class="toolbar">
      <span class="total-badge">共 {{ total }} 条</span>
      <n-button type="primary" size="small" @click="openNew">新增</n-button>
    </div>

    <div v-if="loading" class="loading-container">
      <n-spin size="medium" />
    </div>
    <div v-else-if="items.length === 0" class="empty-state">
      <p>暂无数据，请先导入</p>
    </div>
    <n-data-table v-else :columns="columns" :data="items" :bordered="false" :single-line="false" size="small" />

    <div class="pagination" v-if="total > pageSize">
      <n-button size="small" :disabled="page <= 1" @click="page--; load()">上一页</n-button>
      <span class="page-info">第 <b>{{ page }}</b> 页 / {{ totalPages }} 页 · 共 {{ total }} 条</span>
      <n-input v-model:value="jumpPage" placeholder="" style="width: 60px" @keyup.enter="jumpToPage" />
      <n-button size="small" :disabled="!jumpPage" @click="jumpToPage">跳转</n-button>
      <n-button size="small" :disabled="page >= totalPages" @click="page++; load()">下一页</n-button>
    </div>

    <n-modal v-model:show="showForm" :title="editingId ? '编辑景点' : '新增景点'" preset="dialog" positive-text="保存" negative-text="取消" @positive-click="submitForm" @negative-click="showForm=false">
      <div class="form-body">
        <n-form-item label="名称" path="name">
          <n-input v-model:value="form.name" placeholder="必填" />
        </n-form-item>
        <n-form-item label="城市" path="city">
          <n-input v-model:value="form.city" placeholder="必填" />
        </n-form-item>
        <n-form-item label="分类" path="category">
          <n-radio-group v-model:value="form.category">
            <n-radio value="attraction" label="景点" />
            <n-radio value="food" label="美食" />
            <n-radio value="hotel" label="酒店" />
          </n-radio-group>
        </n-form-item>
        <n-form-item label="描述" path="description">
          <n-input v-model:value="form.description" type="textarea" rows="3" placeholder="必填" />
        </n-form-item>
        <n-form-item label="评分" path="rating">
          <n-input-number v-model:value="form.rating" placeholder="0~5" :min="0" :max="5" :step="0.1" style="width: 120px" />
        </n-form-item>
        <n-form-item label="均价" path="avgCost">
          <n-input-number v-model:value="form.avgCost" placeholder="元" :min="0" style="width: 120px">
            <template #suffix>元</template>
          </n-input-number>
        </n-form-item>
        <n-form-item label="建议时长" path="duration">
          <n-input v-model:value="form.duration" placeholder="如：2-3小时" />
        </n-form-item>
        <n-form-item label="开放时间" path="openTime">
          <n-input v-model:value="form.openTime" placeholder="如：08:00-18:00" />
        </n-form-item>
        <n-form-item label="标签" path="tags">
          <div class="tag-editor">
            <n-tag v-for="(t, i) in form.tags" :key="i" closable @close="removeTag(i)" class="tag-item">{{ t }}</n-tag>
            <n-input v-model:value="tagInput" placeholder="输入标签" @keyup.enter="addTag" style="flex:1;min-width:100px" />
          </div>
        </n-form-item>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.knowledge-page {
  max-width: 900px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.page-title {
  font-size: 22px;
  font-weight: 700;
  margin: 0 0 20px;
  color: var(--text-primary);
}

.filters {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.total-badge {
  font-size: 13px;
  color: var(--text-secondary);
}

.loading-container {
  display: flex;
  justify-content: center;
  padding: 40px;
}

.empty-state {
  text-align: center;
  padding: 40px;
  color: var(--text-secondary);
  font-size: 14px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 20px 0;
}

.page-info {
  font-size: 13px;
  color: var(--text-secondary);
}

.form-body {
  padding: 8px 0;
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
</style>