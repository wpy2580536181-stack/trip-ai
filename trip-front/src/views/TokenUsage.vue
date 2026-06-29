<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import {
  getMyTokenStats,
  getGlobalTokenStats,
  getMyTokenLogs,
  getGlobalTokenLogs,
} from '@/api/tokenUsage'
import type { TokenUsageStats, TokenUsageLogEntry } from '@/api/tokenUsage'
import { get } from '@/api/request'

const message = useMessage()

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

const activeTab = ref<'user' | 'global'>('user')
const isAdmin = computed(() => {
  const stored = typeof window !== 'undefined' ? localStorage.getItem('userInfo') : null
  if (!stored) return false
  try {
    return JSON.parse(stored).roleId === 1
  } catch {
    return false
  }
})

const loading = ref(false)
const stats = ref<TokenUsageStats | null>(null)
const logs = ref<TokenUsageLogEntry[]>([])
const highTokenCases = ref<HighTokenCase[]>([])

const cacheStats = computed(() => {
  let total = 0
  let cached = 0
  let withCached = 0
  for (const l of logs.value) {
    if ((l as any).cached !== undefined) withCached++
    total += l.tokens
    cached += (l as any).cached ?? 0
  }
  return {
    total,
    cached,
    hitRate: total > 0 ? cached / total : 0,
    withCached,
  }
})

const windowPercent = computed(() => {
  if (!stats.value) return 0
  const { current, limit } = stats.value.window
  return limit > 0 ? Math.min(100, Math.round((current / limit) * 100)) : 0
})

const resetInText = computed(() => {
  if (!stats.value) return ''
  const ms = stats.value.window.resetAt - Date.now()
  if (ms <= 0) return '即将重置'
  const mins = Math.floor(ms / 60000)
  if (mins > 0) return `${mins}分钟后重置`
  return `${Math.floor(ms / 1000)}秒后重置`
})

const fetchData = async () => {
  loading.value = true
  try {
    const scope = activeTab.value
    const statsReq = scope === 'global' ? getGlobalTokenStats() : getMyTokenStats()
    const logsReq = scope === 'global' ? getGlobalTokenLogs(50) : getMyTokenLogs(50)
    const [sRes, lRes]: any = await Promise.all([statsReq, logsReq])
    if (sRes?.code === 200) stats.value = sRes.data
    if (lRes?.code === 200) logs.value = lRes.data
  } catch {
    message.error('加载失败')
  } finally {
    loading.value = false
  }
}

const onTabChange = () => {
  stats.value = null
  logs.value = []
  fetchData()
}

const fetchHighTokenCases = async () => {
  if (!isAdmin.value) return
  try {
    const res: any = await get('/feedback/admin/high-token-low-satisfaction', { days: 7, limit: 20 })
    if (res?.code === 200) highTokenCases.value = res.data
  } catch (e) {
    console.warn('fetch high token cases failed', e)
  }
}

const formatTime = (ts: number) => {
  const d = new Date(ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

const formatNum = (n: number) => n.toLocaleString('zh-CN')

const endpointLabels: Record<string, string> = {
  chat: '对话',
  recommend: '推荐',
  optimize: '优化',
  background: '后台任务',
}

onMounted(() => {
  fetchData()
  fetchHighTokenCases()
})
</script>

<template>
  <div class="page-container token-page">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">←</button>
      <h2>Token 用量</h2>
      <div class="header-right">
        <n-button quaternary circle @click="fetchData">
          <template #icon>
            <span>🔄</span>
          </template>
        </n-button>
      </div>
    </div>

    <n-tabs v-model:value="activeTab" @update:value="onTabChange" animated>
      <n-tab name="user" tab="个人"></n-tab>
      <n-tab v-if="isAdmin" name="global" tab="全局"></n-tab>
    </n-tabs>

    <div class="content">
      <div v-if="stats" class="card">
        <div class="stat-row">
          <span class="label">窗口用量</span>
          <span class="value">{{ formatNum(stats.window.current) }} / {{ formatNum(stats.window.limit) }}</span>
        </div>
        <n-progress
          :percentage="windowPercent"
          :color="windowPercent > 80 ? '#d03050' : '#665CA2'"
          :height="8"
          :border-radius="4"
        />
        <div class="stat-row sub">
          <span class="label">窗口重置</span>
          <span class="value">{{ resetInText }}</span>
        </div>
        <div class="stat-row">
          <span class="label">自服务启动累计</span>
          <span class="value">{{ formatNum(stats.totalSinceStart) }}</span>
        </div>
      </div>

      <div class="card cache-card">
        <div class="cache-header">
          <span class="cache-title">LLM Prompt 缓存命中率</span>
          <span class="cache-sub">DeepSeek 自动缓存（系统提示 + 工具）</span>
        </div>
        <div class="cache-rate">
          <span class="cache-rate-num">{{ (cacheStats.hitRate * 100).toFixed(1) }}%</span>
          <span class="cache-rate-detail">
            命中 {{ formatNum(cacheStats.cached) }} / {{ formatNum(cacheStats.total) }} tokens
          </span>
        </div>
        <n-progress
          :percentage="Number((cacheStats.hitRate * 100).toFixed(1))"
          :color="cacheStats.hitRate > 0.7 ? '#18a058' : cacheStats.hitRate > 0.4 ? '#f0a020' : '#d03050'"
          :height="8"
          :border-radius="4"
        />
        <div class="cache-hint">
          命中率越高越省 token 钱。{{ cacheStats.withCached }} 次调用有 cached 数据。
        </div>
      </div>

      <div class="logs-section">
        <div class="section-title">最近调用</div>
        <div v-if="logs.length === 0" class="empty-state">
          <span class="empty-icon">📊</span>
          <p>暂无调用记录</p>
        </div>
        <div v-else class="log-list">
          <div v-for="(log, i) in logs" :key="i" class="log-item">
            <div class="log-row">
              <span class="log-time">{{ formatTime(log.timestamp) }}</span>
              <span class="log-endpoint">{{ endpointLabels[log.endpoint] || log.endpoint }}</span>
              <span class="log-tokens">{{ formatNum(log.tokens) }}</span>
            </div>
          </div>
        </div>
        <div class="hint">仅展示最近调用记录，服务重启后清零</div>
      </div>

      <div v-if="isAdmin" class="cases-section">
        <div class="section-title">高 token + 低满意度案例（7 天）</div>
        <div v-if="highTokenCases.length === 0" class="empty-state">
          <span class="empty-icon">🔍</span>
          <p>暂无负反馈 + token 数据</p>
        </div>
        <div v-else class="case-list">
          <div v-for="(c, i) in highTokenCases" :key="c.feedbackId" class="case-item" :class="{ 'with-border': i < highTokenCases.length - 1 }">
            <div class="case-header">
              <span class="case-user">{{ c.user.nickname || c.user.username }}</span>
              <span class="case-time">{{ formatTime(Date.parse(c.createdAt)) }}</span>
              <span v-if="c.usage" class="case-tokens">{{ formatNum(c.usage.total) }}</span>
              <span v-else class="case-tokens no-usage">无 usage</span>
            </div>
            <div v-if="c.usage" class="case-meta">
              <span class="case-meta-item">prompt {{ formatNum(c.usage.prompt) }}</span>
              <span class="case-meta-item">completion {{ formatNum(c.usage.completion) }}</span>
              <span
                class="case-meta-item"
                :class="c.usage.cacheHitRate > 0.7 ? 'cache-good' : c.usage.cacheHitRate > 0.3 ? 'cache-mid' : 'cache-low'"
              >cache {{ (c.usage.cacheHitRate * 100).toFixed(0) }}%</span>
            </div>
            <div class="case-preview">{{ c.messagePreview }}</div>
            <div v-if="c.comment" class="case-comment">用户原话：{{ c.comment }}</div>
            <div v-if="c.tags && c.tags.length" class="case-tags">
              <n-tag
                v-for="t in c.tags"
                :key="t"
                type="error"
                size="small"
                class="case-tag"
              >{{ t }}</n-tag>
            </div>
          </div>
        </div>
        <div class="hint">按 token 降序排前 20 — 优化 ROI 最高的 case</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.token-page {
  width: 100%;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  background: transparent;
  border-bottom: 1px solid var(--border-color);
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary, #2B2D31);
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
  color: var(--text-primary, #2B2D31);
  line-height: 1;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.card {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}

.stat-row.sub {
  padding-top: 12px;
}

.stat-row .label {
  color: var(--text-secondary, #6C6E74);
  font-size: 14px;
}

.stat-row .value {
  color: var(--text-primary, #2B2D31);
  font-size: 14px;
  font-weight: 500;
}

.section-title {
  font-size: 14px;
  color: var(--text-secondary, #6C6E74);
  margin: 8px 4px;
}

.hint {
  text-align: center;
  color: var(--text-secondary, #6C6E74);
  font-size: 12px;
  margin-top: 12px;
  opacity: 0.6;
}

.log-list {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
}

.log-item {
  padding: 12px 16px;
}

.log-item + .log-item {
  border-top: 1px solid var(--border-color, #EAE5E0);
}

.log-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.log-time {
  color: var(--text-secondary, #6C6E74);
  font-size: 13px;
  min-width: 80px;
}

.log-endpoint {
  flex: 1;
  color: var(--text-primary, #2B2D31);
  font-size: 14px;
}

.log-tokens {
  color: var(--accent, #665CA2);
  font-size: 14px;
  font-weight: 500;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-secondary, #6C6E74);
}

.empty-icon {
  font-size: 36px;
  display: block;
  margin-bottom: 12px;
}

.empty-state p {
  margin: 0;
  font-size: 14px;
}

.cases-section {
  margin-top: 16px;
}

.case-list {
  background: transparent;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  overflow: hidden;
}

.case-item {
  padding: 12px 16px;
}

.case-item.with-border {
  border-bottom: 1px solid var(--border-color, #EAE5E0);
}

.cache-card {
  border-left: 3px solid #18a058;
}

.cache-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
}

.cache-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary, #2B2D31);
}

.cache-sub {
  font-size: 11px;
  color: var(--text-secondary, #6C6E74);
}

.cache-rate {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
}

.cache-rate-num {
  font-size: 24px;
  font-weight: 700;
  color: #18a058;
  font-family: 'SF Mono', Consolas, monospace;
}

.cache-rate-detail {
  font-size: 12px;
  color: var(--text-secondary, #6C6E74);
  font-family: 'SF Mono', Consolas, monospace;
}

.cache-hint {
  font-size: 11px;
  color: var(--text-secondary, #6C6E74);
  margin-top: 8px;
}

.case-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 4px;
}

.case-user {
  color: var(--text-primary, #2B2D31);
  font-weight: 500;
}

.case-time {
  color: var(--text-secondary, #6C6E74);
  font-size: 12px;
  flex: 1;
}

.case-tokens {
  color: #d03050;
  font-weight: 600;
  font-size: 14px;
  font-family: 'SF Mono', Consolas, monospace;
}

.case-tokens.no-usage {
  color: var(--text-secondary, #6C6E74);
  font-size: 12px;
  font-weight: 400;
}

.case-preview {
  color: var(--text-secondary, #6C6E74);
  font-size: 12px;
  line-height: 1.4;
  max-height: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  margin: 4px 0;
}

.case-comment {
  color: #c0392b;
  font-size: 12px;
  font-style: italic;
  margin: 4px 0;
}

.case-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  font-family: 'SF Mono', Consolas, monospace;
  margin: 4px 0;
}

.case-meta-item {
  background: var(--border-color, #EAE5E0);
  padding: 1px 6px;
  border-radius: 3px;
  color: var(--text-secondary, #6C6E74);
}

.case-meta-item.cache-good {
  background: #d5f4e6;
  color: #186a3b;
}

.case-meta-item.cache-mid {
  background: #fef5e7;
  color: #9a7d0a;
}

.case-meta-item.cache-low {
  background: #fadbd8;
  color: #922b21;
}

.case-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.case-tag {
  font-size: 11px;
}
</style>
