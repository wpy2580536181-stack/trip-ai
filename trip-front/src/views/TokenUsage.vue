<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { showToast } from 'vant'
import {
  getMyTokenStats,
  getGlobalTokenStats,
  getMyTokenLogs,
  getGlobalTokenLogs,
} from '@/api/tokenUsage'
import type { TokenUsageStats, TokenUsageLogEntry } from '@/api/tokenUsage'
import { get } from '@/api/request'

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

// 本次 chat 的 prompt cache 命中率（来自 SSE complete event 的 usage.cached）
// 这里只展示 "近 N 次累计"（从 logs 聚合）
const cacheStats = computed(() => {
  let total = 0
  let cached = 0
  let withCached = 0
  for (const l of logs.value) {
    // 老 entries 没 cached 字段（undefined），新 entries 有
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
    showToast('加载失败')
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
    // silent — admin 视角，非阻塞
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
      <van-nav-bar title="Token 用量" left-arrow @click-left="$router.back()">
        <template #right>
          <van-icon name="replay" size="20" @click="fetchData" />
        </template>
      </van-nav-bar>
    </div>

    <van-tabs v-model:active="activeTab" @change="onTabChange" sticky>
      <van-tab title="个人" name="user" />
      <van-tab v-if="isAdmin" title="全局" name="global" />
    </van-tabs>

    <div class="content">
      <div v-if="stats" class="stats-card">
        <div class="stat-row">
          <span class="label">窗口用量</span>
          <span class="value">{{ formatNum(stats.window.current) }} / {{ formatNum(stats.window.limit) }}</span>
        </div>
        <van-progress
          :percentage="windowPercent"
          :show-pivot="true"
          :color="windowPercent > 80 ? '#ee0a24' : '#1989fa'"
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

      <!-- LLM Prompt Cache 命中率（DeepSeek 自动缓存 system prompt + tools） -->
      <div class="cache-card">
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
        <van-progress
          :percentage="cacheStats.hitRate * 100"
          :show-pivot="false"
          :color="cacheStats.hitRate > 0.7 ? '#07c160' : cacheStats.hitRate > 0.4 ? '#ff976a' : '#ee0a24'"
        />
        <div class="cache-hint">
          命中率越高越省 token 钱。{{ cacheStats.withCached }} 次调用有 cached 数据。
        </div>
      </div>

      <div class="logs-section">
        <div class="section-title">最近调用</div>
        <van-empty v-if="logs.length === 0" description="暂无调用记录" />
        <van-cell-group v-else inset>
          <van-cell v-for="(log, i) in logs" :key="i">
            <template #title>
              <div class="log-row">
                <span class="log-time">{{ formatTime(log.timestamp) }}</span>
                <span class="log-endpoint">{{ endpointLabels[log.endpoint] || log.endpoint }}</span>
                <span class="log-tokens">{{ formatNum(log.tokens) }}</span>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
        <div class="hint">仅展示最近调用记录，服务重启后清零</div>
      </div>

      <!-- Admin 视角：高 token + 低满意度案例 -->
      <div v-if="isAdmin" class="cases-section">
        <div class="section-title">高 token + 低满意度案例（7 天）</div>
        <van-empty v-if="highTokenCases.length === 0" description="暂无负反馈 + token 数据" />
        <van-cell-group v-else inset>
          <van-cell v-for="(c, i) in highTokenCases" :key="c.feedbackId" :border="i < highTokenCases.length - 1">
            <template #title>
              <div class="case-row">
                <div class="case-header">
                  <span class="case-user">{{ c.user.nickname || c.user.username }}</span>
                  <span class="case-time">{{ formatTime(Date.parse(c.createdAt)) }}</span>
                  <span v-if="c.usage" class="case-tokens">
                    {{ formatNum(c.usage.total) }}
                  </span>
                  <span v-else class="case-tokens no-usage">无 usage</span>
                </div>
                <div v-if="c.usage" class="case-meta">
                  <span class="case-meta-item">prompt {{ formatNum(c.usage.prompt) }}</span>
                  <span class="case-meta-item">completion {{ formatNum(c.usage.completion) }}</span>
                  <span
                    class="case-meta-item"
                    :class="c.usage.cacheHitRate > 0.7 ? 'cache-good' : c.usage.cacheHitRate > 0.3 ? 'cache-mid' : 'cache-low'"
                  >
                    cache {{ (c.usage.cacheHitRate * 100).toFixed(0) }}%
                  </span>
                </div>
                <div class="case-preview">{{ c.messagePreview }}</div>
                <div v-if="c.comment" class="case-comment">用户原话：{{ c.comment }}</div>
                <div v-if="c.tags && c.tags.length" class="case-tags">
                  <van-tag
                    v-for="t in c.tags"
                    :key="t"
                    type="danger"
                    plain
                    size="mini"
                    class="case-tag"
                  >{{ t }}</van-tag>
                </div>
              </div>
            </template>
          </van-cell>
        </van-cell-group>
        <div class="hint">按 token 降序排前 20 — 优化 ROI 最高的 case</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.token-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f7f8fa;
}
.content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.stats-card {
  background: #fff;
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
  color: #666;
  font-size: 14px;
}
.stat-row .value {
  color: #333;
  font-size: 14px;
  font-weight: 500;
}
.section-title {
  font-size: 14px;
  color: #999;
  margin: 8px 4px;
}
.hint {
  text-align: center;
  color: #c8c9cc;
  font-size: 12px;
  margin-top: 12px;
}
.log-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.log-time {
  color: #999;
  font-size: 13px;
  min-width: 80px;
}
.log-endpoint {
  flex: 1;
  color: #333;
  font-size: 14px;
}
.log-tokens {
  color: #1989fa;
  font-size: 14px;
  font-weight: 500;
}
.cases-section {
  margin-top: 16px;
}
.cache-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 16px;
  border-left: 3px solid #07c160;
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
  color: #333;
}
.cache-sub {
  font-size: 11px;
  color: #999;
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
  color: #07c160;
  font-family: 'SF Mono', Consolas, monospace;
}
.cache-rate-detail {
  font-size: 12px;
  color: #666;
  font-family: 'SF Mono', Consolas, monospace;
}
.cache-hint {
  font-size: 11px;
  color: #999;
  margin-top: 8px;
}
.case-row {
  width: 100%;
}
.case-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 4px;
}
.case-user {
  color: #333;
  font-weight: 500;
}
.case-time {
  color: #999;
  font-size: 12px;
  flex: 1;
}
.case-tokens {
  color: #ee0a24;
  font-weight: 600;
  font-size: 14px;
  font-family: 'SF Mono', Consolas, monospace;
}
.case-tokens.no-usage {
  color: #c8c9cc;
  font-size: 12px;
  font-weight: 400;
}
.case-preview {
  color: #666;
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
  background: #f5f5f5;
  padding: 1px 6px;
  border-radius: 3px;
  color: #666;
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
