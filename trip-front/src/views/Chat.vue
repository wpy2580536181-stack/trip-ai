<script setup lang="ts">
import { ref, watch, nextTick, onBeforeUnmount, onMounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { fetchStream } from '@/api/request'
import ChatBubble from '@/components/ChatBubble.vue'
import { getConversation, listConversations, deleteConversation, type ConversationListItem } from '@/api/conversation'

const message = useMessage()
const dialog = useDialog()

interface TokenUsage {
  prompt: number
  completion: number
  total: number
}

interface Message {
  role: 'user' | 'ai'
  content: string
  timestamp: string
  usage?: TokenUsage
}

const CONVERSATION_ID_KEY = 'trip_chat_conversation_id'

const messages = ref<Message[]>([])
const isStreaming = ref(false)
const inputMessage = ref('')
const toolStatus = ref<string | null>(null)
const connectionWarning = ref<string | null>(null)
const currentAbortController = ref<AbortController | null>(null)
let lastEventTime = 0
let connectionCheckTimer: ReturnType<typeof setInterval> | null = null

const conversationItems = ref<ConversationListItem[]>([])
const loadingConversations = ref(false)

const onEventReceived = () => {
  lastEventTime = Date.now()
  connectionWarning.value = null
}

const startConnectionCheck = () => {
  lastEventTime = Date.now()
  connectionWarning.value = null
  connectionCheckTimer = setInterval(() => {
    if (!isStreaming.value) return
    if (Date.now() - lastEventTime > 10000) {
      connectionWarning.value = '服务器响应较慢，请耐心等待...'
    }
  }, 2000)
}

const stopConnectionCheck = () => {
  if (connectionCheckTimer) {
    clearInterval(connectionCheckTimer)
    connectionCheckTimer = null
  }
  connectionWarning.value = null
}

const toolLabels: Record<string, string> = {
  retrieve_knowledge: '检索知识库',
  get_weather: '查询天气',
  calculate_distance: '计算距离',
  search_hotels: '查询酒店',
}

const stored = typeof window !== 'undefined' ? localStorage.getItem(CONVERSATION_ID_KEY) : null
const parsedStored = stored ? Number(stored) : NaN
const currentConversationId = ref<number | null>(Number.isInteger(parsedStored) ? parsedStored : null)
if (currentConversationId.value == null && typeof window !== 'undefined') {
  localStorage.removeItem(CONVERSATION_ID_KEY)
}

const quickQuestions = ref([
  '北京有哪些必去的景点',
  '上海有哪些热门的美食',
  '成都三日游攻略推荐',
  '如何选择旅游保险',
])

const messageListRef = ref<HTMLElement | null>(null)

const scrollToBottom = () => {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

watch(() => messages.value[messages.value.length - 1]?.content, scrollToBottom)
watch(() => messages.value.length, scrollToBottom)

const handleClick = (question: string) => {
  inputMessage.value = question
  sendMessage()
}

const addUserMessage = (msg: string) => {
  messages.value.push({
    role: 'user',
    content: msg,
    timestamp: new Date().toISOString(),
  })
}

const sendMessage = () => {
  const msg = inputMessage.value.trim()
  if (!msg || isStreaming.value) return
  addUserMessage(msg)
  inputMessage.value = ''
  fetchAiResponse(msg)
}

const stopStreaming = () => {
  currentAbortController.value?.abort()
  currentAbortController.value = null
  isStreaming.value = false
  toolStatus.value = null
  stopConnectionCheck()
}

onBeforeUnmount(() => {
  currentAbortController.value?.abort()
  currentAbortController.value = null
  stopConnectionCheck()
})

const fetchAiResponse = (userMsg: string) => {
  isStreaming.value = true
  toolStatus.value = null
  messages.value.push({
    role: 'ai',
    content: '',
    timestamp: new Date().toISOString(),
  })
  startConnectionCheck()

  fetchStream(
    'trip/chat',
    { message: userMsg, conversationId: currentConversationId.value },
    (chunk) => {
      onEventReceived()
      connectionWarning.value = null
      messages.value[messages.value.length - 1].content += chunk
    },
    (data) => {
      isStreaming.value = false
      toolStatus.value = null
      connectionWarning.value = null
      stopConnectionCheck()
      currentAbortController.value = null
      if (data?.usage && messages.value.length > 0) {
        messages.value[messages.value.length - 1].usage = data.usage
      }
      if (data?.conversationId) {
        currentConversationId.value = data.conversationId
        localStorage.setItem(CONVERSATION_ID_KEY, String(data.conversationId))
      }
      loadConversations()
    },
    (errMsg) => {
      messages.value[messages.value.length - 1].content = `AI处理发生错误: ${errMsg}`
      isStreaming.value = false
      toolStatus.value = null
      connectionWarning.value = null
      stopConnectionCheck()
      currentAbortController.value = null
      message.error('AI处理发生错误')
      loadConversations()
    },
    (type, name) => {
      onEventReceived()
      toolStatus.value = type === 'tool_start' ? (toolLabels[name] || name) : null
    },
    () => {
      onEventReceived()
    },
    (attempt, maxRetries) => {
      connectionWarning.value = `网络中断，正在重连（第 ${attempt}/${maxRetries} 次）...`
    },
  ).then(controller => {
    currentAbortController.value = controller
  })
}

const loadConversations = async () => {
  loadingConversations.value = true
  try {
    const res = await listConversations()
    conversationItems.value = res.data?.items ?? []
  } catch {
    message.error('加载历史对话失败')
  } finally {
    loadingConversations.value = false
  }
}

const onSelectConversation = async (id: number) => {
  try {
    const res = await getConversation(id)
    const conv = res.data
    if (!conv) return
    currentConversationId.value = id
    localStorage.setItem(CONVERSATION_ID_KEY, String(id))
    messages.value = (conv.messages || []).map(m => ({
      id: m.id,
      role: m.role === 'user' ? 'user' : 'ai',
      content: m.content,
      timestamp: m.createdAt,
    }))
    loadConversations()
  } catch {
    message.error('加载对话失败')
  }
}

const onNewConversation = () => {
  currentConversationId.value = null
  localStorage.removeItem(CONVERSATION_ID_KEY)
  messages.value = []
  loadConversations()
}

const onDeleteConversation = (id: number) => {
  dialog.warning({
    title: '确认删除',
    content: '删除后无法恢复',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteConversation(id)
        conversationItems.value = conversationItems.value.filter(i => i.id !== id)
        if (currentConversationId.value === id) {
          onNewConversation()
        }
        message.success('已删除')
      } catch {
        message.error('删除失败')
      }
    },
  })
}

const formatTime = (iso: string) => {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

onMounted(loadConversations)
</script>

<template>
  <div class="chat-layout">
    <aside class="chat-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">对话历史</span>
      </div>
      <div class="sidebar-actions">
        <n-button block size="small" @click="onNewConversation">+ 新建对话</n-button>
      </div>
      <div class="sidebar-body">
        <div v-if="!loadingConversations && conversationItems.length === 0" class="sidebar-empty">
          暂无历史对话
        </div>
        <div v-else class="conversation-list">
          <div
            v-for="item in conversationItems"
            :key="item.id"
            class="conv-item"
            :class="{ active: item.id === currentConversationId }"
            @click="onSelectConversation(item.id)"
          >
            <div class="conv-item-info">
              <div class="conv-item-title">{{ item.title || '新对话' }}</div>
              <div class="conv-item-meta">{{ item._count.messages }} 条 · {{ formatTime(item.updatedAt) }}</div>
            </div>
            <span class="conv-item-delete" @click.stop="onDeleteConversation(item.id)">🗑️</span>
          </div>
        </div>
      </div>
    </aside>

    <div class="chat-main">
      <div class="chat-header">
        <h2 class="chat-title">AI 旅游助手</h2>
      </div>

      <div class="message-container" ref="messageListRef">
        <div v-if="messages.length === 0" class="chat-empty">
          <div class="empty-state">
            <div class="empty-icon">💬</div>
            <p class="empty-text">开始和 AI 助手对话</p>
          </div>
          <div class="quick-questions">
            <div class="quick-title">常见问题</div>
            <div class="quick-tags">
              <n-tag
                v-for="(question, index) in quickQuestions"
                :key="index"
                class="quick-tag"
                @click="handleClick(question)"
              >
                {{ question }}
              </n-tag>
            </div>
          </div>
        </div>

        <div v-else class="message-list">
          <ChatBubble
            v-for="(msg, index) in messages"
            :key="msg.timestamp + '-' + index"
            :message="msg"
            :streaming="isStreaming && index === messages.length - 1 && msg.role === 'ai'"
            :conversation-id="currentConversationId"
          />
          <div v-if="isStreaming" class="streaming-indicator">
            <n-spin size="small" />
            <span v-if="toolStatus">🔍 {{ toolStatus }}...</span>
            <span v-else-if="connectionWarning">{{ connectionWarning }}</span>
            <span v-else>AI 正在思考中</span>
            <n-button size="tiny" @click="stopStreaming" class="stop-btn">停止</n-button>
          </div>
        </div>
      </div>

      <div class="chat-input-area">
        <div class="input-wrapper">
          <n-input
            v-model:value="inputMessage"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 6 }"
            placeholder="请输入问题或指令"
            @keydown.enter.exact.prevent="sendMessage"
          />
          <n-button
            type="primary"
            size="small"
            :disabled="!inputMessage.trim() || isStreaming"
            @click="sendMessage"
          >
            发送
          </n-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 12px;
}

.chat-sidebar {
  width: 280px;
  min-width: 280px;
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  background: var(--bg-secondary);
}

.sidebar-header {
  padding: 20px 16px 12px;
  border-radius: 12px 0 0 0;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.sidebar-actions {
  padding: 0 16px 12px;
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
  border-radius: 0 0 0 12px;
}

.sidebar-empty {
  padding: 32px 16px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 14px;
}

.conversation-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.conv-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  gap: 8px;
}

.conv-item:hover {
  background: var(--hover-bg);
}

.conv-item.active {
  background: var(--hover-bg-active);
}

.conv-item-info {
  flex: 1;
  min-width: 0;
}

.conv-item-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-item.active .conv-item-title {
  color: var(--accent);
}

.conv-item-meta {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.conv-item-delete {
  font-size: 14px;
  opacity: 0;
  transition: opacity 0.15s;
  cursor: pointer;
  flex-shrink: 0;
  line-height: 1;
}

.conv-item:hover .conv-item-delete {
  opacity: 0.6;
}

.conv-item-delete:hover {
  opacity: 1 !important;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  padding: 20px 24px 12px;
  border-bottom: 1px solid var(--border-color);
}

.chat-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.message-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  -webkit-user-select: text;
  user-select: text;
}

.chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
}

.empty-state {
  text-align: center;
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.empty-text {
  font-size: 15px;
  color: var(--text-secondary);
  margin: 0;
}

.quick-questions {
  margin-top: 32px;
  text-align: center;
}

.quick-title {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

.quick-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.quick-tag {
  cursor: pointer;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.streaming-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.stop-btn {
  margin-left: auto;
}

.chat-input-area {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  background: var(--bg-primary);
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-wrapper :deep(.n-input) {
  flex: 1;
}
</style>
