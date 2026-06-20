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

onMounted(fetchData)
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
</style>
