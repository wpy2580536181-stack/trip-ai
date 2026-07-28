<script setup lang="ts">
/**
 * ChatPanel — 嵌入式对话面板组件
 *
 * 从 Chat.vue 抽取核心 SSE 对话逻辑，用于 Detail.vue 侧栏。
 * 复用 ChatBubble.vue 渲染消息，复用 fetchStream 进行流式通信。
 */
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { useMessage } from 'naive-ui'
import { fetchStream } from '@/api/request'
import ChatBubble from '@/components/ChatBubble.vue'

const props = withDefaults(defineProps<{
  tripId?: number | null
  prefill?: string
  compact?: boolean
}>(), {
  tripId: null,
  prefill: '',
  compact: true,
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
const currentAbortController = ref<AbortController | null>(null)
const messageListRef = ref<HTMLElement | null>(null)
const currentConversationId = ref<number | null>(null)

const toolLabels: Record<string, string> = {
  retrieve_knowledge: '检索知识库',
  get_weather: '查询天气',
  calculate_distance: '计算距离',
  search_hotels: '查询酒店',
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
    if (val && !isStreaming.value) {
      inputMessage.value = val
      nextTick(() => sendMessage())
    }
  },
)

const sendMessage = () => {
  const msg = inputMessage.value.trim()
  if (!msg || isStreaming.value) return
  messages.value.push({ role: 'user', content: msg, timestamp: new Date().toISOString() })
  inputMessage.value = ''
  fetchAiResponse(msg)
}

const stopStreaming = () => {
  currentAbortController.value?.abort()
  currentAbortController.value = null
  isStreaming.value = false
  toolStatus.value = null
}

onBeforeUnmount(() => {
  currentAbortController.value?.abort()
  currentAbortController.value = null
})

const fetchAiResponse = (userMsg: string) => {
  isStreaming.value = true
  toolStatus.value = null
  messages.value.push({ role: 'ai', content: '', timestamp: new Date().toISOString() })

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
      currentAbortController.value = null
      if (data?.conversationId) {
        currentConversationId.value = data.conversationId
      }
      // 检测行程修改响应，通知父组件刷新
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg?.content?.includes('"type": "trip_modified"') || lastMsg?.content?.includes('"type":"trip_modified"')) {
        try {
          const jsonStr = lastMsg.content
          const start = jsonStr.indexOf('{')
          const end = jsonStr.lastIndexOf('}')
          if (start !== -1 && end > start) {
            const parsed = JSON.parse(jsonStr.slice(start, end + 1))
            if (parsed.new_trip_id) {
              emit('trip-updated', parsed.new_trip_id)
              // 替换原始 JSON 为友好摘要
              lastMsg.content = parsed.summary || '行程已修改'
            }
          }
        } catch { /* 解析失败不影响主流程 */ }
      }
    },
    (errMsg) => {
      messages.value[messages.value.length - 1].content = `发生错误: ${errMsg}`
      isStreaming.value = false
      toolStatus.value = null
      currentAbortController.value = null
      naiveMessage.error(errMsg || 'AI 处理发生错误')
    },
    (type, name) => {
      toolStatus.value = type === 'tool_start' ? (toolLabels[name] || name) : null
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
    currentAbortController.value = null
    if (err?.name !== 'AbortError') {
      naiveMessage.error('网络连接失败')
    }
  })
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
    </div>

    <div v-if="toolStatus" class="chat-panel-tool-status">
      <span class="tool-dot"></span> {{ toolStatus }}...
    </div>

    <div class="chat-panel-input">
      <n-input
        v-model:value="inputMessage"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 3 }"
        placeholder="输入消息..."
        :disabled="isStreaming"
        @keydown="handleKeydown"
      />
      <n-button
        size="small"
        type="primary"
        :disabled="!inputMessage.trim() || isStreaming"
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
