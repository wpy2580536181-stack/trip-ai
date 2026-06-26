<script setup lang="ts">
/**
 * Admin Agent Trace 页面
 *
 * 功能：
 *  - 按 messageId 查单次 agent 完整 trace
 *  - 按 conversationId 查会话最近 N 条 message 摘要
 *  - 步骤时间轴（van-steps），每步可展开 args / output
 *
 * 鉴权：route meta.requiresAdmin，roleId === 1
 */

import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import {
  fetchAgentTrace,
  fetchAgentTraceSummary,
  type TraceStep,
  type TraceMessage,
  type TraceSummary,
} from '@/api/trace'

const searchMessageId = ref<number | null>(null)
const searchConvId = ref<number | null>(null)
const traceMessage = ref<TraceMessage | null>(null)
const traceSteps = ref<TraceStep[]>([])
const traceSummary = ref<TraceSummary[]>([])
const loading = ref(false)

async function loadTrace() {
  if (!searchMessageId.value) {
    showToast('请输入 messageId')
    return
  }
  loading.value = true
  try {
    const result = await fetchAgentTrace(searchMessageId.value)
    traceMessage.value = result.message
    traceSteps.value = result.steps
    traceSummary.value = []
  } catch (e) {
    showToast('加载 trace 失败：' + ((e as Error).message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  if (!searchConvId.value) {
    showToast('请输入 conversationId')
    return
  }
  loading.value = true
  try {
    traceMessage.value = null
    traceSteps.value = []
    traceSummary.value = await fetchAgentTraceSummary(searchConvId.value)
    if (traceSummary.value.length === 0) {
      showToast('该会话暂无 assistant 消息')
    }
  } catch (e) {
    showToast('加载摘要失败：' + ((e as Error).message || '未知错误'))
  } finally {
    loading.value = false
  }
}

function openFromSummary(s: TraceSummary) {
  searchMessageId.value = s.messageId
  loadTrace()
}

// URL query 自动加载：/admin/trace?messageId=847
const route = useRoute()
if (route.query.messageId) {
  const mid = parseInt(route.query.messageId as string, 10)
  if (!isNaN(mid) && mid > 0) {
    searchMessageId.value = mid
    loadTrace()
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
</script>

<template>
  <div class="page-container admin-trace-page">
    <van-nav-bar title="Agent Trace" left-arrow @click-left="$router.back()">
      <template #right>
        <van-icon name="cluster-o" size="20" @click="$router.push('/admin/architecture')" />
      </template>
    </van-nav-bar>

    <div class="search-bar">
      <van-field
        v-model.number="searchMessageId"
        label="Message ID"
        type="number"
        placeholder="输入 messageId"
        clearable
      />
      <van-button type="primary" size="small" :loading="loading" @click="loadTrace">查看</van-button>
    </div>

    <div class="search-bar">
      <van-field
        v-model.number="searchConvId"
        label="Conv ID"
        type="number"
        placeholder="输入 conversationId 查列表"
        clearable
      />
      <van-button type="primary" size="small" :loading="loading" @click="loadSummary">查列表</van-button>
    </div>

    <div v-if="traceMessage" class="trace-detail">
      <van-cell-group inset>
        <van-cell title="Message ID" :value="String(traceMessage.id)" />
        <van-cell title="Role" :value="traceMessage.role" />
        <van-cell title="Steps" :value="String(traceMessage._count.steps)" />
        <van-cell title="Created" :value="formatTime(traceMessage.createdAt)" />
        <van-cell title="Content">
          <template #value>
            <div class="content-preview">{{ traceMessage.content.slice(0, 300) }}</div>
          </template>
        </van-cell>
      </van-cell-group>

      <h3 class="section-title">Step 时间轴（{{ traceSteps.length }}）</h3>
      <div v-if="traceSteps.length === 0" class="empty">该 message 暂无步骤记录</div>
      <van-steps v-else direction="vertical" :active="traceSteps.length - 1">
        <van-step v-for="step in traceSteps" :key="step.id">
          <h4 class="step-title">
            #{{ step.step }} · {{ step.type }}<span v-if="step.name">: {{ step.name }}</span>
          </h4>
          <div v-if="step.durationMs !== null" class="meta">耗时：{{ step.durationMs }}ms</div>
          <div v-if="step.error" class="error">Error: {{ step.error }}</div>
          <van-collapse v-if="step.args || step.output" class="step-collapse">
            <van-collapse-item v-if="step.args" :title="`args`" :name="`args-${step.id}`">
              <pre class="json">{{ JSON.stringify(step.args, null, 2) }}</pre>
            </van-collapse-item>
            <van-collapse-item v-if="step.output" :title="`output`" :name="`output-${step.id}`">
              <pre class="json">{{ step.output }}</pre>
            </van-collapse-item>
          </van-collapse>
        </van-step>
      </van-steps>
    </div>

    <div v-else-if="traceSummary.length > 0" class="summary-list">
      <h3 class="section-title">会话 #{{ searchConvId }} 最近消息（{{ traceSummary.length }}）</h3>
      <van-cell-group inset>
        <van-cell
          v-for="s in traceSummary"
          :key="s.messageId"
          :title="`#${s.messageId} · ${s.stepCount} steps`"
          :label="s.preview"
          is-link
          @click="openFromSummary(s)"
        />
      </van-cell-group>
    </div>
  </div>
</template>

<style scoped>
.admin-trace-page { padding: 16px; }
.search-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
  background: #fff;
  border-radius: 8px;
  padding: 4px 8px;
}
.search-bar :deep(.van-field) { flex: 1; }
.section-title {
  margin: 16px 4px 8px;
  font-size: 15px;
  font-weight: 600;
  color: #323233;
}
.content-preview {
  font-size: 12px;
  color: #666;
  max-width: 220px;
  word-break: break-all;
  white-space: pre-wrap;
  text-align: left;
}
.step-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 500;
}
.meta { color: #999; font-size: 12px; margin-top: 2px; }
.error { color: #ee0a24; font-size: 12px; margin-top: 2px; word-break: break-all; }
.step-collapse { margin-top: 6px; }
.json {
  background: #f7f8fa;
  padding: 8px;
  border-radius: 4px;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.empty {
  text-align: center;
  color: #999;
  padding: 24px 0;
  font-size: 13px;
}
</style>
