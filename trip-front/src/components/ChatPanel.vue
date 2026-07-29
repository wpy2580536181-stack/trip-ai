<script setup lang="ts">
/**
 * ChatPanel — 嵌入式对话面板组件
 *
 * 从 Chat.vue 抽取核心 SSE 对话逻辑，用于 Detail.vue 侧栏。
 * 复用 ChatBubble.vue 渲染消息，复用 fetchStream 进行流式通信。
 */
import { ref, computed, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { useMessage } from 'naive-ui'
import { fetchStream } from '@/api/request'
import { getConversation } from '@/api/conversation'
import ChatBubble from '@/components/ChatBubble.vue'
import TripDiffCard from '@/components/TripDiffCard.vue'
import PoiListCard from '@/components/PoiListCard.vue'
import CommuteCard from '@/components/CommuteCard.vue'

const props = withDefaults(defineProps<{
  tripId?: number | null
  prefill?: string
  compact?: boolean
  disabled?: boolean
}>(), {
  tripId: null,
  prefill: '',
  compact: true,
  disabled: false,
})

const emit = defineEmits<{
  (e: 'trip-updated', data: any): void
}>()

const naiveMessage = useMessage()

interface Message {
  role: 'user' | 'ai'
  content: string
  timestamp: string
}

const messages = ref<Message[]>([])
const isStreaming = ref(false)
const inputMessage = ref('')
const toolStatus = ref<string | null>(null)
const progressData = ref<{ stage: string; status: string } | null>(null)
const diffCards = ref<Map<number, { newTripId: number; parentTripId: number; changes: any[] }>>(new Map())
const cardData = ref<Map<number, { type: string; data: any }>>(new Map())
const currentAbortController = ref<AbortController | null>(null)
const messageListRef = ref<HTMLElement | null>(null)
const currentConversationId = ref<number | null>(null)

// 行程修改后→详情页切换完成前的窗口期，禁止再发消息（避免基于旧 tripId 分叉版本）
const awaitingTripSwitch = ref(false)
watch(
  () => props.tripId,
  (newId, oldId) => {
    awaitingTripSwitch.value = false
    // 版本切换：同一会话跨版本延续，把会话 ID 迁到新 tripId 的 key
    if (newId && newId !== oldId && currentConversationId.value) {
      persistConversationId(newId, currentConversationId.value)
    }
  },
)

const inputDisabled = computed(() => props.disabled || awaitingTripSwitch.value)

// ---- 会话持久化（按 tripId 维度，刷新详情页后可恢复） ----
const convStorageKey = (tripId: number) => `trip_panel_conv_${tripId}`

const persistConversationId = (tripId: number, convId: number) => {
  try {
    localStorage.setItem(convStorageKey(tripId), String(convId))
  } catch { /* ignore */ }
}

const restoreConversation = async () => {
  if (!props.tripId) return
  let stored: string | null = null
  try {
    stored = localStorage.getItem(convStorageKey(props.tripId))
  } catch { /* ignore */ }
  const convId = stored ? Number(stored) : NaN
  if (!Number.isInteger(convId) || convId <= 0) return
  try {
    const res = await getConversation(convId)
    const conv = res.data
    if (!conv) return
    currentConversationId.value = convId
    messages.value = (conv.messages || [])
      .filter(m => m.role !== 'system' && m.content)
      .map(m => ({
        role: m.role === 'user' ? 'user' as const : 'ai' as const,
        content: m.content,
        timestamp: m.createdAt,
      }))
  } catch {
    // 会话已删除/无权限：清 key，从空会话开始
    try {
      localStorage.removeItem(convStorageKey(props.tripId))
    } catch { /* ignore */ }
  }
}

onMounted(restoreConversation)

const stageOrder = ['research', 'plan', 'review']

const currentStageLabel = computed(() => {
  const ps = progressData.value
  if (!ps) return ''
  const labels = stageLabels[ps.stage]
  return labels?.[ps.status] || ps.stage
})

const progressWidth = computed(() => {
  const ps = progressData.value
  if (!ps || ps.status !== 'start') return 0
  const idx = stageOrder.indexOf(ps.stage)
  if (idx < 0) return 0
  return ((idx + 1) / stageOrder.length) * 100
})

const toolLabels: Record<string, string> = {
  retrieve_knowledge: '检索知识库',
  get_weather: '查询天气',
  calculate_distance: '计算距离',
  search_hotels: '查询酒店',
}

const stageLabels: Record<string, Record<string, string>> = {
  research: { start: '正在搜索景点信息…', done: '搜索完成' },
  plan: { start: '正在规划行程…', done: '规划完成' },
  review: { start: '正在校验预算与路线…', done: '校验完成' },
}

const scrollToBottom = () => {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

watch(() => messages.value[messages.value.length - 1]?.content, scrollToBottom)
watch(() => messages.value.length, scrollToBottom)

// prefill 变化时自动发送
watch(
  () => props.prefill,
  (val) => {
    if (val && !isStreaming.value && !inputDisabled.value) {
      inputMessage.value = val
      nextTick(() => sendMessage())
    }
  },
)

const sendMessage = () => {
  const msg = inputMessage.value.trim()
  if (!msg || isStreaming.value || inputDisabled.value) return
  messages.value.push({ role: 'user', content: msg, timestamp: new Date().toISOString() })
  inputMessage.value = ''
  fetchAiResponse(msg)
}

const stopStreaming = () => {
  currentAbortController.value?.abort()
  currentAbortController.value = null
  isStreaming.value = false
  toolStatus.value = null
  progressData.value = null
}

onBeforeUnmount(() => {
  currentAbortController.value?.abort()
  currentAbortController.value = null
})

const fetchAiResponse = (userMsg: string) => {
  isStreaming.value = true
  toolStatus.value = null
  progressData.value = null
  messages.value.push({ role: 'ai', content: '', timestamp: new Date().toISOString() })

  // 对话内全量规划：只附详情链接，不切换当前行程
  let tripPlannedData: { newTripId: number; summary?: string } | null = null

  fetchStream(
    'trip/chat',
    {
      message: userMsg,
      conversationId: currentConversationId.value,
      tripId: props.tripId,
    },
    (chunk) => {
      messages.value[messages.value.length - 1].content += chunk
    },
    (data) => {
      isStreaming.value = false
      toolStatus.value = null
      progressData.value = null
      currentAbortController.value = null
      if (data?.conversationId) {
        currentConversationId.value = data.conversationId
        if (props.tripId) {
          persistConversationId(props.tripId, data.conversationId)
        }
      }
      if (tripPlannedData) {
        // 新规划行程：回填摘要 + 详情链接，不影响当前正在看的行程
        const lastMsg = messages.value[messages.value.length - 1]
        const link = `[查看行程详情](/detail?id=${tripPlannedData.newTripId})`
        if (lastMsg && lastMsg.role === 'ai') {
          lastMsg.content = lastMsg.content
            ? `${lastMsg.content}\n\n${link}`
            : `${tripPlannedData.summary || '行程已生成'}\n\n${link}`
        }
      }
    },
    (errMsg) => {
      messages.value[messages.value.length - 1].content = `发生错误: ${errMsg}`
      isStreaming.value = false
      toolStatus.value = null
      progressData.value = null
      currentAbortController.value = null
      naiveMessage.error(errMsg || 'AI 处理发生错误')
    },
    (type, name) => {
      toolStatus.value = type === 'tool_start' ? (toolLabels[name] || name) : null
    },
    undefined, // onHeartbeat
    undefined, // onResume
    {
      onTripEvent: (type, data) => {
        if (type === 'trip_diff' && data?.changes && data?.newTripId) {
          const idx = messages.value.length - 1
          diffCards.value.set(idx, {
            newTripId: data.newTripId,
            parentTripId: data.parentTripId,
            changes: data.changes,
          })
        } else if (type === 'trip_planned' && data?.newTripId && data.newTripId !== tripPlannedData?.newTripId) {
          tripPlannedData = { newTripId: data.newTripId, summary: data.summary }
        }
      },
      onProgress: (data) => {
        if (data?.stage && data?.status) {
          progressData.value = { stage: data.stage, status: data.status }
        }
      },
      onCard: (cardType, data) => {
        const idx = messages.value.length - 1
        cardData.value.set(idx, { type: cardType, data })
      },
    },
  ).then(controller => {
    currentAbortController.value = controller
  }).catch((err) => {
    // 网络级错误（连接失败、超时等）
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg && lastMsg.role === 'ai' && !lastMsg.content) {
      lastMsg.content = '网络连接失败，请重试'
    }
    isStreaming.value = false
    toolStatus.value = null
    progressData.value = null
    currentAbortController.value = null
    if (err?.name !== 'AbortError') {
      naiveMessage.error('网络连接失败')
    }
  })
}

const onDiffConfirm = (tripId: number) => {
  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg && lastMsg.role === 'ai' && !lastMsg.content) {
    lastMsg.content = '已采纳修改方案，正在切换…'
  }
  awaitingTripSwitch.value = true
  emit('trip-updated', tripId)
  diffCards.value = new Map()
}

const onDiffCancel = () => {
  const lastMsg = messages.value[messages.value.length - 1]
  if (lastMsg && lastMsg.role === 'ai' && !lastMsg.content) {
    lastMsg.content = '已取消修改'
  }
  diffCards.value = new Map()
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <div class="chat-panel" :class="{ compact }">
    <div class="chat-panel-header">
      <span class="chat-panel-title">AI 旅行助手</span>
      <span v-if="tripId" class="chat-panel-badge">行程 #{{ tripId }}</span>
    </div>

    <div ref="messageListRef" class="chat-panel-messages">
      <div v-if="messages.length === 0" class="chat-panel-empty">
        <p>有什么可以帮你的？</p>
        <p class="chat-panel-hint">可以问我行程调整、附近美食、通勤路线等问题</p>
      </div>
      <ChatBubble
        v-for="(msg, idx) in messages"
        :key="idx"
        :message="msg"
        :streaming="isStreaming && idx === messages.length - 1 && msg.role === 'ai'"
      />
      <TripDiffCard
        v-if="diffCards.has(messages.length - 1)"
        :newTripId="diffCards.get(messages.length - 1)!.newTripId"
        :parentTripId="diffCards.get(messages.length - 1)!.parentTripId"
        :changes="diffCards.get(messages.length - 1)!.changes"
        @confirm="onDiffConfirm"
        @cancel="onDiffCancel"
      />
      <PoiListCard
        v-if="cardData.has(messages.length - 1) && cardData.get(messages.length - 1)!.type === 'poi_list'"
        :items="cardData.get(messages.length - 1)!.data.items || []"
      />
      <CommuteCard
        v-if="cardData.has(messages.length - 1) && cardData.get(messages.length - 1)!.type === 'commute_compare'"
        :options="cardData.get(messages.length - 1)!.data.options || []"
        :recommended="cardData.get(messages.length - 1)!.data.recommended"
      />
    </div>

    <div v-if="toolStatus" class="chat-panel-tool-status">
      <span class="tool-dot"></span> {{ toolStatus }}...
    </div>

    <div v-if="progressData?.status === 'start'" class="chat-panel-progress">
      <div class="progress-bar">
        <div class="progress-fill" :style="{ width: progressWidth + '%' }"></div>
      </div>
      <span class="progress-label">{{ currentStageLabel }}</span>
    </div>

    <div class="chat-panel-input">
      <n-input
        v-model:value="inputMessage"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 3 }"
        :placeholder="inputDisabled ? '行程更新中…' : '输入消息...'"
        :disabled="isStreaming || inputDisabled"
        @keydown="handleKeydown"
      />
      <n-button
        size="small"
        type="primary"
        :disabled="!inputMessage.trim() || isStreaming || inputDisabled"
        @click="sendMessage"
      >
        发送
      </n-button>
      <n-button
        v-if="isStreaming"
        size="small"
        quaternary
        @click="stopStreaming"
      >
        停止
      </n-button>
    </div>
  </div>
</template>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  border-left: 1px solid var(--n-border-color, #e8e8e8);
  background: var(--n-color, #fff);
}

.chat-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--n-border-color, #e8e8e8);
  flex-shrink: 0;
}

.chat-panel-title {
  font-weight: 600;
  font-size: 14px;
}

.chat-panel-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #e6f7ff;
  color: #1890ff;
}

.chat-panel-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  min-height: 0;
}

.chat-panel-empty {
  text-align: center;
  color: #999;
  padding: 40px 16px;
  font-size: 13px;
}

.chat-panel-hint {
  font-size: 12px;
  color: #bbb;
  margin-top: 8px;
}

.chat-panel-tool-status {
  padding: 4px 16px;
  font-size: 12px;
  color: #1890ff;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tool-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1890ff;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.chat-panel-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  font-size: 12px;
  color: #666;
}

.progress-bar {
  flex: 1;
  height: 4px;
  border-radius: 2px;
  background: #f0f0f0;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 2px;
  background: #1890ff;
  transition: width 0.3s ease;
}

.progress-label {
  white-space: nowrap;
  min-width: 100px;
  text-align: right;
}

.chat-panel-input {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--n-border-color, #e8e8e8);
  flex-shrink: 0;
}

.chat-panel-input .n-input {
  flex: 1;
}
</style>
