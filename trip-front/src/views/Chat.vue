<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { showToast } from 'vant'
import { fetchStream } from '@/api/request'
import ChatBubble from '@/components/ChatBubble.vue'
import ConversationDrawer from '@/components/ConversationDrawer.vue'
import { getConversation } from '@/api/conversation'

const router = useRouter()

interface Message {
  role: 'user' | 'ai'
  content: string
  timestamp: string
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

const onBack = () => router.back()

const handleClick = (question: string) => {
  inputMessage.value = question
  sendMessage()
}

const addUserMessage = (message: string) => {
  messages.value.push({
    role: 'user',
    content: message,
    timestamp: new Date().toISOString(),
  })
}

const sendMessage = () => {
  const message = inputMessage.value.trim()
  if (!message || isStreaming.value) return
  addUserMessage(message)
  inputMessage.value = ''
  fetchAiResponse(message)
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
      messages.value[messages.value.length - 1].content += chunk
    },
    (data) => {
      isStreaming.value = false
      toolStatus.value = null
      stopConnectionCheck()
      currentAbortController.value = null
      if (data?.conversationId) {
        currentConversationId.value = data.conversationId
        localStorage.setItem(CONVERSATION_ID_KEY, String(data.conversationId))
      }
      refreshSidebar()
    },
    (errMsg) => {
      messages.value[messages.value.length - 1].content = `AI处理发生错误: ${errMsg}`
      isStreaming.value = false
      toolStatus.value = null
      stopConnectionCheck()
      currentAbortController.value = null
      showToast('AI处理发生错误')
      refreshSidebar()
    },
    (type, name) => {
      onEventReceived()
      toolStatus.value = type === 'tool_start' ? (toolLabels[name] || name) : null
    },
    () => {
      onEventReceived()
    },
  ).then(controller => {
    currentAbortController.value = controller
  })
}

const showDrawer = ref(false)
const sidebarRef = ref<InstanceType<typeof ConversationDrawer> | null>(null)

const refreshSidebar = () => {
  if (sidebarRef.value) {
    sidebarRef.value.refresh()
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
      role: m.role === 'user' ? 'user' : 'ai',
      content: m.content,
      timestamp: m.createdAt,
    }))
    refreshSidebar()
  } catch (e) {
    showToast('加载对话失败')
  }
}

const onNewConversation = () => {
  currentConversationId.value = null
  localStorage.removeItem(CONVERSATION_ID_KEY)
  messages.value = []
  refreshSidebar()
}
</script>

<template>
  <div class="page-container chat-page">
    <div class="page-header">
      <van-nav-bar
        left-arrow
        left-text="返回"
        @click-left="onBack"
        title="AI 旅游助手"
      >
        <template #right>
          <van-icon name="bars" size="20" @click="showDrawer = true" />
        </template>
      </van-nav-bar>
    </div>
    <div class="chat-container" ref="messageListRef">
      <div class="chat-empty" v-if="messages.length === 0">
        <van-empty description="开始和ai助手对话"></van-empty>
        <div class="quick-questions">
          <div class="quick-title">常见问题</div>
          <van-tag
            v-for="(question, index) in quickQuestions"
            :key="index"
            size="large"
            class="quick-tag"
            @click="handleClick(question)"
          >
            {{ question }}
          </van-tag>
        </div>
      </div>

      <div v-else class="message-list">
        <ChatBubble
          v-for="(message, index) in messages"
          :key="message.timestamp + '-' + index"
          :message="message"
          :streaming="isStreaming && index === messages.length - 1 && message.role === 'ai'"
        />
        <div class="streaming-indicator" v-if="isStreaming">
          <van-loading type="spinner" size="20px" />
          <span v-if="toolStatus">🔍 {{ toolStatus }}...</span>
          <span v-else-if="connectionWarning">{{ connectionWarning }}</span>
          <span v-else>AI正在思考中</span>
          <van-button size="mini" plain type="danger" @click="stopStreaming" class="stop-btn">停止</van-button>
        </div>
      </div>
    </div>
    <div class="chat-input-area">
      <van-field
        v-model="inputMessage"
        placeholder="请输入问题或指令"
        @keyup.enter="sendMessage"
      >
        <template #button>
          <van-button
            type="primary"
            size="small"
            @click="sendMessage"
            :disabled="!inputMessage.trim()"
          >
            发送
          </van-button>
        </template>
      </van-field>
    </div>
    <ConversationDrawer
      ref="sidebarRef"
      v-model:show="showDrawer"
      :active-conversation-id="currentConversationId"
      @select="onSelectConversation"
      @new="onNewConversation"
    />
  </div>
</template>

<style scoped>
.page-header {
  height: 46px;
}
.chat-page {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding-bottom: 50px;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  padding-bottom: 60px;
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

.quick-questions {
  margin-top: 32px;
  text-align: center;
}

.quick-title {
  font-size: 14px;
  color: #999;
  margin-bottom: 16px;
}

.quick-tag {
  margin: 8px;
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
  padding: 8px 16px;
  color: #999;
  font-size: 14px;
}

.stop-btn {
  margin-left: auto;
}

.chat-input-area {
  position: fixed;
  bottom: 50px;
  left: 0;
  right: 0;
  background: #fff;
  padding: 8px 16px;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.05);
  max-width: 750px;
  margin: 0 auto;
}

.chat-input-area :deep(.van-field) {
  background: #f7f8fa;
  border-radius: 20px;
  padding: 8px 16px;
}
</style>
