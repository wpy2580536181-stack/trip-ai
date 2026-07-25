<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import {
  useMessage,
  useDialog,
  NButton,
  NTabs,
  NTabPane,
  NSelect,
  type DataTableColumn,
} from 'naive-ui'
import {
  listSpots,
  createSpot,
  updateSpot,
  deleteSpot,
  listSpotDocs,
  type SpotItem,
  type SpotInput,
  type SpotDocItem,
} from '@/api/knowledge'

const message = useMessage()
const dialog = useDialog()

const activeTab = ref<'spots' | 'docs'>('spots')

/* ---------------- 景点（事实层 spots） ---------------- */
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
        items.value = items.value.filter((i) => i.id !== id)
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
    render: (row: SpotItem) => (row.rating ? `${row.rating}分` : '-'),
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

/* ---------------- 文本层 / 维基（spot_docs） ---------------- */
const docs = ref<SpotDocItem[]>([])
const loadingDocs = ref(false)
const docsTotal = ref(0)
const docsPage = ref(1)
const docsPageSize = 20
const docsTotalPages = computed(() => Math.ceil(docsTotal.value / docsPageSize))

const chromaInfo = ref<{ available: boolean; spotDocsCount: number | null }>({
  available: false,
  spotDocsCount: null,
})

const docFilterCity = ref('')
const docFilterSource = ref<string | null>(null)
const docSourceOptions = [
  { label: '全部来源', value: '' },
  { label: '维基百科', value: 'wiki' },
  { label: 'Wikidata', value: 'wikidata' },
  { label: '高德详情', value: 'gaode_detail' },
  { label: '官方来源', value: 'official_gov' },
]

const loadDocs = async () => {
  loadingDocs.value = true
  try {
    const res = await listSpotDocs({
      city: docFilterCity.value || undefined,
      sourceType: docFilterSource.value || undefined,
      page: docsPage.value,
      pageSize: docsPageSize,
    })
    docs.value = res.data?.items ?? []
    docsTotal.value = res.data?.total ?? 0
    chromaInfo.value = res.data?.chroma ?? { available: false, spotDocsCount: null }
  } catch {
    message.error('加载文本层失败')
  } finally {
    loadingDocs.value = false
  }
}

const docJumpPage = ref('')
const docJumpToPage = () => {
  const p = Number(docJumpPage.value)
  if (p >= 1 && p <= docsTotalPages.value && p !== docsPage.value) {
    docsPage.value = p
    loadDocs()
  }
  docJumpPage.value = ''
}

const onTabChange = (val: string) => {
  if (val === 'docs' && docs.value.length === 0) loadDocs()
}

const docColumns: DataTableColumn[] = [
  { title: '关联景点', key: 'spotName', ellipsis: { tooltip: true } },
  { title: '城市', key: 'city', width: 90 },
  {
    title: '来源',
    key: 'sourceType',
    width: 100,
    render: (row: SpotDocItem) => row.sourceType || '-',
  },
  {
    title: '标题',
    key: 'title',
    width: 150,
    ellipsis: { tooltip: true },
    render: (row: SpotDocItem) => row.title || '-',
  },
  {
    title: '内容预览',
    key: 'content',
    ellipsis: { tooltip: true },
  },
  {
    title: '可信度',
    key: 'credibilityScore',
    width: 80,
    render: (row: SpotDocItem) =>
      row.credibilityScore != null ? row.credibilityScore.toFixed(2) : '-',
  },
  {
    title: '向量ID',
    key: 'vectorId',
    width: 90,
    render: (row: SpotDocItem) =>
      row.vectorId ? '已分配' : '无',
  },
]

onMounted(load)
</script>

<template>
  <div class="knowledge-page">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">←</button>
      <h2>知识库管理</h2>
      <div class="header-right">
        <n-button v-if="activeTab === 'spots'" type="primary" size="small" @click="openNew">
          新增
        </n-button>
      </div>
    </div>

    <n-tabs v-model:value="activeTab" type="line" @update:value="onTabChange">
      <!-- 事实层：景点 -->
      <n-tab-pane name="spots" tab="景点">
        <div class="filters">
          <div class="filter-row">
            <n-input
              v-model:value="filterCity"
              placeholder="筛选城市"
              clearable
              @update:value="page = 1; load()"
              style="width: 200px"
            />
            <n-radio-group v-model:value="filterCategory" @update:value="page = 1; load()">
              <n-radio v-for="opt in categoryOptions" :key="opt.value" :value="opt.value" :label="opt.text" />
            </n-radio-group>
          </div>
        </div>

        <div class="toolbar">
          <span class="total-badge">共 {{ total }} 条</span>
        </div>

        <div v-if="loading" class="loading-container">
          <n-spin size="medium" />
        </div>
        <div v-else-if="items.length === 0" class="empty-state">
          <p>暂无数据，请先导入</p>
        </div>
        <n-data-table
          v-else
          :columns="columns"
          :data="items"
          :bordered="false"
          :single-line="false"
          size="small"
        />

        <div class="pagination" v-if="total > pageSize">
          <n-button size="small" :disabled="page <= 1" @click="page--; load()">上一页</n-button>
          <span class="page-info">第 <b>{{ page }}</b> 页 / {{ totalPages }} 页 · 共 {{ total }} 条</span>
          <n-input v-model:value="jumpPage" placeholder="" style="width: 60px" @keyup.enter="jumpToPage" />
          <n-button size="small" :disabled="!jumpPage" @click="jumpToPage">跳转</n-button>
          <n-button size="small" :disabled="page >= totalPages" @click="page++; load()">下一页</n-button>
        </div>
      </n-tab-pane>

      <!-- 文本层：维基等外部语料 -->
      <n-tab-pane name="docs" tab="文本层 / 维基">
        <div class="filters">
          <div class="filter-row">
            <n-input
              v-model:value="docFilterCity"
              placeholder="按城市筛选"
              clearable
              @update:value="docsPage = 1; loadDocs()"
              style="width: 200px"
            />
            <n-select
              v-model:value="docFilterSource"
              :options="docSourceOptions"
              placeholder="来源类型"
              clearable
              style="width: 160px"
              @update:value="docsPage = 1; loadDocs()"
            />
            <n-button size="small" @click="loadDocs()">刷新</n-button>
          </div>
        </div>

        <div class="toolbar">
          <span class="total-badge">共 {{ docsTotal }} 块文本</span>
          <span class="hint">
            Chroma：<b :style="{ color: chromaInfo.available ? '#3FA66A' : '#E0A23B' }">{{
              chromaInfo.available ? `可用（${chromaInfo.spotDocsCount ?? 0} 条）` : '当前不可用'
            }}</b>
            · 向量ID「已分配」≠ 已在向量库，需安装 torch 后重跑入库才会真正入 Chroma
          </span>
        </div>

        <div v-if="loadingDocs" class="loading-container">
          <n-spin size="medium" />
        </div>
        <div v-else-if="docs.length === 0" class="empty-state">
          <p>暂无文本层数据</p>
        </div>
        <n-data-table
          v-else
          :columns="docColumns"
          :data="docs"
          :bordered="false"
          :single-line="false"
          size="small"
        />

        <div class="pagination" v-if="docsTotal > docsPageSize">
          <n-button size="small" :disabled="docsPage <= 1" @click="docsPage--; loadDocs()">上一页</n-button>
          <span class="page-info">第 <b>{{ docsPage }}</b> 页 / {{ docsTotalPages }} 页 · 共 {{ docsTotal }} 块</span>
          <n-input v-model:value="docJumpPage" placeholder="" style="width: 60px" @keyup.enter="docJumpToPage" />
          <n-button size="small" :disabled="!docJumpPage" @click="docJumpToPage">跳转</n-button>
          <n-button size="small" :disabled="docsPage >= docsTotalPages" @click="docsPage++; loadDocs()">下一页</n-button>
        </div>
      </n-tab-pane>
    </n-tabs>

    <n-modal
      v-model:show="showForm"
      :title="editingId ? '编辑景点' : '新增景点'"
      preset="dialog"
      positive-text="保存"
      negative-text="取消"
      @positive-click="submitForm"
      @negative-click="showForm = false"
    >
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

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  border-radius: 12px 12px 0 0;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.header-right {
  margin-left: auto;
}

.back-btn {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  padding: 0;
  color: var(--text-primary);
  line-height: 1;
}

.filters {
  margin: 16px 20px 0;
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
  margin: 16px 20px 0;
  gap: 12px;
}

.total-badge {
  font-size: 13px;
  color: var(--text-secondary);
}

.hint {
  font-size: 12px;
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
