<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ref, watch, nextTick } from 'vue'
import { showToast } from 'vant'
import { fetchStream } from '@/api/request'
import ChatBubble from '@/components/ChatBubble.vue'

const router = useRouter()

const onBack = () => {
  router.back()
}
//会话数据
interface Message {
  role: 'user' | 'ai'
  content: string
  timestamp: string
}
const messages = ref<Message[]>([])
//常见问题
const quickQuestions = ref([
  '北京有哪些必去的景点',
  '上海有哪些热门的美食',
  '成都三日游攻略推荐',
  '如何选择旅游保险'
])
//点击标签事件
const handleClick = (question: string) => {
  inputMessage.value = question
  sendMessage()
}

//输入框内容
const inputMessage = ref('')

//发送消息事件
const sendMessage = () => {
  //去空格处理
  const message = inputMessage.value.trim()
  //调用接口前判断数据是否存在，并且AI不在处理中
  if(!message || isStreaming.value){
    return
  }
  addUserMessage(message)
  //清空输入框
  inputMessage.value = ''
  //调用AI接口,进行流式请求
  fetchAiResponse(message)
}

//获取AI的响应
const fetchAiResponse = (userMsg: string) => {
  isStreaming.value = true
  messages.value.push({
    role: 'ai',
    content: '',
    timestamp: new Date().toISOString()
  })

  let fullResponse = ''

  fetchStream(
    'trip/chat',
    { message: userMsg, conversationId: currentConversationId.value },
    (chunk) => {
      fullResponse += chunk
      const lastMessage = messages.value[messages.value.length - 1]
      if(lastMessage && lastMessage.role === 'ai'){
        lastMessage.content = fullResponse
      }
    },
    (data) => {
      isStreaming.value = false
      if (data?.conversationId) {
        currentConversationId.value = data.conversationId
        localStorage.setItem(CONVERSATION_ID_KEY, String(data.conversationId))
      }
    },
    (errMsg) => {
    const lastMessage = messages.value[messages.value.length - 1]
    if(lastMessage && lastMessage.role === 'ai'){
      lastMessage.content = `AI处理发生错误:${errMsg}`
    }
    isStreaming.value = false
    showToast('AI处理发生错误')
     })


}

//AI处理中的状态
const isStreaming = ref(false)

//当前会话ID（首次响应后由后端返回；持久化到 localStorage 以防刷新丢失）
// TODO(phase-1.5): 替换为会话列表侧边栏，支持多会话切换
const CONVERSATION_ID_KEY = 'trip_chat_conversation_id'
const stored = typeof window !== 'undefined' ? localStorage.getItem(CONVERSATION_ID_KEY) : null
const currentConversationId = ref<number | null>(stored ? Number(stored) : null)
if (currentConversationId.value && !Number.isInteger(currentConversationId.value)) {
  currentConversationId.value = null
  if (typeof window !== 'undefined') localStorage.removeItem(CONVERSATION_ID_KEY)
}

//消息列表容器引用
const messageListRef = ref<HTMLElement | null>(null)

//自动滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

//监控messages变化，自动滚动到底部
watch(() => messages.value[messages.value.length - 1]?.content, scrollToBottom)
watch(() => messages.value.length, scrollToBottom)

//用户发送消息
const addUserMessage = (message: string) => {
  messages.value.push({
    role: 'user',
    content: message,
    timestamp: new Date().toISOString()
  })
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
      />
    </div>
    <div class="chat-container" ref="messageListRef">
      <div class="chat-empty" v-if="messages.length === 0">
        <van-empty description="开始和ai助手对话"></van-empty>
        <div class="quick-questions">
        <div class="quick-title">常见问题</div>
        <van-tag v-for="(question,index) in quickQuestions" size="large" :key="index" class="quick-tag" @click="handleClick(question)">
          {{ question }} 
        </van-tag>
      </div>
      </div>
      
      <div v-else class="message-list"> 
        <ChatBubble v-for="message in messages" :key="message.timestamp" :message="message" />
        <div class="streaming-indicator" v-if="isStreaming">
          <van-loading type="spinner" size="20px" />
          <span>AI正在思考中</span>
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
        <van-button type="primary" size="small" @click="sendMessage" :disabled="!inputMessage.trim()">发送</van-button>
      </template>
      </van-field>
    </div>
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
