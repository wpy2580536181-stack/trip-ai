<script setup lang="ts">
/**
 * Admin Feedback Dashboard
 *
 * 数据：
 *  - /api/feedback/stats?days=7
 *  - /api/feedback/admin/daily-stats?days=30
 *  - /api/feedback/admin/high-token-low-satisfaction?days=7&limit=20
 *
 * 鉴权：route meta.requiresAdmin，roleId 必须 === 1
 */

import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { get } from '@/api/request'
import { convertFeedbackToFixture, type ConvertToFixtureResponse } from '@/api/feedback'

const message = useMessage()

interface GlobalStats {
  totalCount: number
  upCount: number
  downCount: number
  satisfactionRate: number
  recentDownComments: Array<{ comment: string; tags: string[] | null; createdAt: string }>
}

interface DailyStat {
  date: string
  up: number
  down: number
  total: number
  satisfactionRate: number
}

interface HighTokenCase {
  feedbackId: number
  messageId: number
  rating: number
  comment: string | null
  tags: string[] | null
  user: { id: number; username: string; nickname: string | null }
  messagePreview: string
  usage: { prompt: number; completion: number; total: number; cached: number; cacheHitRate: number } | null
  createdAt: string
}

const router = useRouter()
const days = ref<7 | 30>(7)
const loading = ref(false)

const globalStats = ref<GlobalStats | null>(null)
const dailyStats = ref<DailyStat[]>([])
const highTokenCases = ref<HighTokenCase[]>([])

const fetchAll = async () => {
  loading.value = true
  try {
    const [statsRes, dailyRes, casesRes]: any[] = await Promise.all([
      get('/feedback/stats', { days: days.value }),
      get('/feedback/admin/daily-stats', { days: days.value }),
      get('/feedback/admin/high-token-low-satisfaction', { days: days.value, limit: 20 }),
    ])
    if (statsRes?.code === 200) globalStats.value = statsRes.data
    if (dailyRes?.code === 200) dailyStats.value = dailyRes.data
    if (casesRes?.code === 200) highTokenCases.value = casesRes.data
  } catch (e) {
    message.error('加载失败：' + ((e as Error).message || '未知错误'))
  } finally {
    loading.value = false
  }
}

watch(days, () => fetchAll())
onMounted(fetchAll)

// === computed ===
const satisfactionColor = computed(() => {
  const r = globalStats.value?.satisfactionRate ?? 0
  if (r >= 0.8) return '#07c160'
  if (r >= 0.5) return '#ff976a'
  return '#ee0a24'
})

// 趋势图：归一化高度（van-progress 不支持多 bar，用 CSS 自绘）
const dailyChart = computed(() => {
  const data = dailyStats.value
  if (data.length === 0) return null
  const max = Math.max(1, ...data.map((d) => d.total))
  return data.map((d) => ({
    ...d,
    upHeightPct: (d.up / max) * 100,
    downHeightPct: (d.down / max) * 100,
  }))
})

// 高 token 案例聚合 stats
const caseAggregate = computed(() => {
  const cases = highTokenCases.value
  let totalTokens = 0
  let avgCacheRate = 0
  let withUsage = 0
  for (const c of cases) {
    if (c.usage) {
      totalTokens += c.usage.total
      avgCacheRate += c.usage.cacheHitRate
      withUsage++
    }
  }
  return {
    caseCount: cases.length,
    totalTokens,
    avgCacheRate: withUsage > 0 ? avgCacheRate / withUsage : 0,
  }
})

const formatNum = (n: number) => n.toLocaleString('zh-CN')
const formatTime = (ts: number) => {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
const formatDate = (d: string) => {
  // '2026-06-24' -> '6/24'
  const parts = d.split('-')
  return `${parseInt(parts[1])}/${parseInt(parts[2])}`
}

const onBack = () => router.back()

function goTrace(messageId: number) {
  router.push(`/admin/trace?messageId=${messageId}`)
}

// === fixture 转换 ===
const showConvertModal = ref(false)
const convertResult = ref<ConvertToFixtureResponse>({ files: [], skipped: [] })
const converting = ref(false)

async function convertOne(feedbackId: number) {
  if (converting.value) return
  converting.value = true
  try {
    const res: any = await convertFeedbackToFixture([feedbackId])
    if (res?.code === 200) {
      convertResult.value = res.data
      showConvertModal.value = true
      if (res.data.files.length > 0) message.success(`已生成 ${res.data.files.length} 个 fixture`)
      else message.warning('未生成任何 fixture（可能 feedback 不存在）')
    } else {
      message.error('转换失败：' + (res?.error || res?.message || '未知错误'))
    }
  } catch (e) {
    message.error('转换失败：' + ((e as Error).message || '未知错误'))
  } finally {
    converting.value = false
  }
}

async function convertBatch() {
  const allIds = (highTokenCases.value || []).map((c) => c.feedbackId)
  if (allIds.length === 0) {
    message.warning('当前没有负反馈案例')
    return
  }
  if (converting.value) return
  converting.value = true
  try {
    const res: any = await convertFeedbackToFixture(allIds)
    if (res?.code === 200) {
      convertResult.value = res.data
      showConvertModal.value = true
      message.success(`已生成 ${res.data.files.length} 个 fixture${res.data.skipped.length > 0 ? `（跳过 ${res.data.skipped.length}）` : ''}`)
    } else {
      message.error('批量转换失败：' + (res?.error || res?.message || '未知错误'))
    }
  } catch (e) {
    message.error('批量转换失败：' + ((e as Error).message || '未知错误'))
  } finally {
    converting.value = false
  }
}
</script>

<template>
  <div class="admin-page">
    <div class="page-header">
      <button class="back-btn" @click="onBack">←</button>
      <h2>反馈 Dashboard</h2>
      <div class="header-right">
        <n-button quaternary circle @click="fetchAll" title="刷新">
          <template #icon><span>🔄</span></template>
        </n-button>
        <n-button quaternary circle @click="$router.push('/admin/architecture')" title="架构图">
          <template #icon><span>🏗</span></template>
        </n-button>
      </div>
    </div>

    <div class="content">
      <!-- 时间窗口选择 -->
      <n-tabs v-model:value="days" @update:value="fetchAll">
        <n-tab name="7" tab="近 7 天" />
        <n-tab name="30" tab="近 30 天" />
      </n-tabs>

      <!-- 4 个数字卡片 -->
      <div v-if="globalStats" class="stats-grid">
        <n-card class="stat-card" size="small" :bordered="true">
          <div class="stat-label">总反馈</div>
          <div class="stat-value">{{ formatNum(globalStats.totalCount) }}</div>
        </n-card>
        <n-card class="stat-card" size="small" :style="{ borderLeft: `3px solid ${satisfactionColor}` }">
          <div class="stat-label">满意率</div>
          <div class="stat-value" :style="{ color: satisfactionColor }">
            {{ (globalStats.satisfactionRate * 100).toFixed(1) }}%
          </div>
        </n-card>
        <n-card class="stat-card" size="small">
          <div class="stat-label">👍</div>
          <div class="stat-value up">{{ formatNum(globalStats.upCount) }}</div>
        </n-card>
        <n-card class="stat-card" size="small">
          <div class="stat-label">👎</div>
          <div class="stat-value down">{{ formatNum(globalStats.downCount) }}</div>
        </n-card>
      </div>

      <!-- 趋势图 -->
      <div class="section-card">
        <div class="section-title">每日反馈趋势（{{ days }} 天）</div>
        <div v-if="dailyChart" class="chart">
          <div class="chart-row">
            <div
              v-for="d in dailyChart"
              :key="d.date"
              class="chart-bar"
            >
              <div class="bar-stack">
                <div
                  class="bar-up"
                  :style="{ height: d.upHeightPct + '%' }"
                  :title="`${d.date} 👍 ${d.up} 👎 ${d.down}`"
                />
                <div
                  class="bar-down"
                  :style="{ height: d.downHeightPct + '%' }"
                />
              </div>
              <div class="bar-label">{{ formatDate(d.date) }}</div>
            </div>
          </div>
          <div class="chart-legend">
            <span class="legend-item"><span class="legend-dot up" />👍</span>
            <span class="legend-item"><span class="legend-dot down" />👎</span>
          </div>
        </div>
      </div>

      <!-- 最近负反馈评论 -->
      <div v-if="globalStats && globalStats.recentDownComments.length" class="section-card">
        <div class="section-title">最近负反馈评论</div>
        <div class="comment-list">
          <div
            v-for="(c, i) in globalStats.recentDownComments"
            :key="i"
            class="comment-item"
          >
            <div class="comment-meta">
              <span class="comment-time">{{ formatTime(Date.parse(c.createdAt)) }}</span>
              <n-tag
                v-for="t in (c.tags || []).slice(0, 3)"
                :key="t"
                type="error"
                size="small"
                :bordered="false"
              >{{ t }}</n-tag>
            </div>
            <div class="comment-text">{{ c.comment }}</div>
          </div>
        </div>
      </div>

      <!-- 高 token + 低满意度案例 -->
      <div v-if="highTokenCases.length" class="section-card">
        <div class="section-title">
          高 token + 低满意度案例
          <span class="section-sub">（{{ caseAggregate.caseCount }} 个 / 总 {{ formatNum(caseAggregate.totalTokens) }} tokens / 平均 cache {{ (caseAggregate.avgCacheRate * 100).toFixed(0) }}%）</span>
        </div>
        <n-button
          block
          secondary
          :loading="converting"
          :disabled="converting"
          @click="convertBatch"
          style="margin-bottom: 12px"
        >
          批量转最近 {{ days }} 天负反馈为 fixture
        </n-button>
        <div class="case-list">
          <div
            v-for="c in highTokenCases"
            :key="c.feedbackId"
            class="case-item"
          >
            <div class="case-header">
              <span class="case-user">{{ c.user.nickname || c.user.username }}</span>
              <span class="case-time">{{ formatTime(Date.parse(c.createdAt)) }}</span>
              <span v-if="c.usage" class="case-tokens">{{ formatNum(c.usage.total) }}</span>
            </div>
            <div v-if="c.usage" class="case-meta">
              <span class="meta-item">prompt {{ formatNum(c.usage.prompt) }}</span>
              <span class="meta-item">completion {{ formatNum(c.usage.completion) }}</span>
              <span
                class="meta-item"
                :class="c.usage.cacheHitRate > 0.7 ? 'cache-good' : c.usage.cacheHitRate > 0.3 ? 'cache-mid' : 'cache-low'"
              >
                cache {{ (c.usage.cacheHitRate * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="case-preview">{{ c.messagePreview }}</div>
            <div v-if="c.comment" class="case-comment">用户：{{ c.comment }}</div>
            <div class="case-actions">
              <n-button
                size="tiny"
                secondary
                :loading="converting"
                :disabled="converting"
                @click="convertOne(c.feedbackId)"
              >
                📋 转 fixture
              </n-button>
              <n-button
                size="tiny"
                quaternary
                @click="goTrace(c.messageId)"
              >
                🔍 Trace
              </n-button>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="!loading && globalStats && globalStats.totalCount === 0"
        class="empty-state"
      >
        <p>近 {{ days }} 天还没有反馈</p>
      </div>
    </div>

    <n-modal
      v-model:show="showConvertModal"
      title="Fixture 骨架已生成"
      preset="card"
      style="width: 600px; max-width: 90vw;"
      :mask-closable="false"
    >
      <div>
        <p>已生成 <strong>{{ convertResult.files.length }}</strong> 个文件：</p>
        <ul v-if="convertResult.files.length" style="padding-left: 20px; margin: 8px 0">
          <li
            v-for="f in convertResult.files"
            :key="f"
            style="font-family: monospace; font-size: 12px; word-break: break-all; margin-bottom: 4px; color: var(--text-secondary)"
          >
            {{ f }}
          </li>
        </ul>
        <p v-if="convertResult.skipped.length" style="color: #d03050; margin-top: 12px; font-size: 13px">
          跳过 {{ convertResult.skipped.length }} 条：
        </p>
        <ul v-if="convertResult.skipped.length" style="padding-left: 20px; margin: 4px 0">
          <li
            v-for="s in convertResult.skipped"
            :key="s.id"
            style="font-size: 12px; margin-bottom: 2px"
          >
            feedback #{{ s.id }}: {{ s.reason }}
          </li>
        </ul>
        <p style="color: var(--text-secondary); font-size: 12px; margin-top: 12px">
          请到 IDE 编辑文件，补 expected 段后 commit。
        </p>
      </div>
      <template #footer>
        <n-button @click="showConvertModal = false">完成</n-button>
      </template>
    </n-modal>
  </div>
</template>

<style scoped>
.admin-page {
  min-height: 100vh;
  background: #f5f7fa;
  border: 1px solid var(--border-color);
  border-radius: 12px;
}
.content {
  padding: 12px;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px;
  border-left: 3px solid #1989fa;
}
.stat-label {
  font-size: 12px;
  color: #999;
  margin-bottom: 4px;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #2c3e50;
  font-family: 'SF Mono', Consolas, monospace;
}
.stat-value.up { color: #07c160; }
.stat-value.down { color: #ee0a24; }
.section {
  background: #fff;
  border-radius: 10px;
  padding: 14px;
  margin-bottom: 16px;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
}
.section-sub {
  font-size: 11px;
  color: #999;
  font-weight: 400;
  margin-left: 6px;
}
.chart {
  padding: 8px 0;
}
.chart-row {
  display: flex;
  align-items: flex-end;
  height: 100px;
  gap: 2px;
}
.chart-bar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
}
.bar-stack {
  flex: 1;
  width: 80%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 1px;
}
.bar-up {
  background: #07c160;
  border-radius: 2px 2px 0 0;
  min-height: 1px;
}
.bar-down {
  background: #ee0a24;
  border-radius: 0 0 2px 2px;
  min-height: 0;
}
.bar-label {
  font-size: 9px;
  color: #999;
  margin-top: 2px;
  font-family: 'SF Mono', Consolas, monospace;
}
.chart-legend {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 8px;
  font-size: 11px;
  color: #666;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.legend-dot.up { background: #07c160; }
.legend-dot.down { background: #ee0a24; }
.comment-list, .case-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.comment-item {
  background: #fafafa;
  border-radius: 6px;
  padding: 8px 10px;
  border-left: 2px solid #ee0a24;
}
.comment-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #999;
  margin-bottom: 4px;
}
.comment-time {
  font-family: 'SF Mono', Consolas, monospace;
}
.comment-text {
  font-size: 13px;
  color: #555;
  line-height: 1.4;
}
.case-item {
  background: #fafafa;
  border-radius: 6px;
  padding: 10px;
  border-left: 3px solid #ee0a24;
}
.case-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 4px;
}
.case-user {
  color: #333;
  font-weight: 500;
}
.case-time {
  color: #999;
  flex: 1;
}
.case-tokens {
  color: #ee0a24;
  font-weight: 600;
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 13px;
}
.case-meta {
  display: flex;
  gap: 6px;
  font-size: 11px;
  font-family: 'SF Mono', Consolas, monospace;
  margin-bottom: 4px;
}
.meta-item {
  background: #fff;
  padding: 1px 5px;
  border-radius: 3px;
  color: #666;
  border: 1px solid #eee;
}
.meta-item.cache-good {
  background: #d5f4e6;
  color: #186a3b;
  border-color: transparent;
}
.meta-item.cache-mid {
  background: #fef5e7;
  color: #9a7d0a;
  border-color: transparent;
}
.meta-item.cache-low {
  background: #fadbd8;
  color: #922b21;
  border-color: transparent;
}
.case-preview {
  color: #666;
  font-size: 12px;
  line-height: 1.4;
  max-height: 50px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.case-comment {
  color: #c0392b;
  font-size: 12px;
  font-style: italic;
  margin-top: 4px;
}
.case-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
</style>
