<template>
  <div class="chat-bubble" :class="messageClass">
    <div class="bubble-content">
      <div class="message-text" v-if="message.role === 'user'">{{ message.content }}</div>
      <div
        class="message-text ai-message markdown-body"
        v-else
        :class="{ 'streaming-raw': streaming }"
        v-html="renderedContent"
      ></div>
    </div>
    <div class="bubble-footer" v-if="message.role === 'ai' && message.id && !streaming">
      <button
        v-for="btn in feedbackButtons"
        :key="btn.value"
        class="feedback-btn"
        :class="{ active: currentRating === btn.value }"
        :title="btn.title"
        :disabled="submitting"
        @click="onFeedback(btn.value)"
      >
        <span class="emoji">{{ btn.emoji }}</span>
        <span v-if="currentRating === btn.value" class="rating-label">{{ btn.label }}</span>
      </button>
      <span v-if="submitted" class="feedback-thanks">已收到反馈</span>
    </div>
    <div class="message-time" v-if="showTime">{{ formatTime }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { marked } from 'marked'
import { useMessage } from 'naive-ui'
import { submitFeedback, type FeedbackRating } from '@/api/feedback'

const message = useMessage()

marked.setOptions({
  breaks: true,
  gfm: true,
})

interface Message {
  id?: number
  role: 'user' | 'ai'
  content: string
  timestamp?: string
}

const props = defineProps<{
  message: Message
  streaming?: boolean
  conversationId?: number
}>()

const submitting = ref(false)
const submitted = ref(false)
const currentRating = ref<FeedbackRating | null>(null)

const feedbackButtons = [
  { value: 1 as FeedbackRating, emoji: '👍', label: '有用', title: '这条回复对我有帮助' },
  { value: -1 as FeedbackRating, emoji: '👎', label: '没用', title: '这条回复对我没帮助' },
]

const messageClass = computed(() => {
  return props.message.role === 'user' ? 'user-message' : 'ai-message'
})

const escapeHtml = (s: string) =>
  s.replace(/[&<>"']/g, c => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]!))

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  if (props.streaming) {
    const tail = escapeHtml(props.message.content)
    return `${tail}<span class="streaming-cursor">▍</span>`
  }
  return marked.parse(props.message.content) as string
})

const showTime = computed(() => {
  return props.message.timestamp && props.message.content
})

const formatTime = computed(() => {
  if (!props.message.timestamp) return ''
  const date = new Date(props.message.timestamp)
  return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
})

const onFeedback = async (rating: FeedbackRating) => {
  if (!props.message.id || !props.conversationId) {
    message.warning('消息未保存，无法反馈')
    return
  }
  // 切换：再点同一按钮取消（可选优化，先做单次提交）
  if (submitting.value) return

  submitting.value = true
  try {
    await submitFeedback({
      messageId: props.message.id,
      conversationId: props.conversationId,
      rating,
    })
    currentRating.value = rating
    submitted.value = true
    if (rating === -1) {
      // 负反馈：3 秒后弹"为什么不满意"轻量提示
      setTimeout(() => {
        if (currentRating.value === -1) {
          message.warning('抱歉没能帮到你，可联系 admin@trip.local 详细反馈', {
            duration: 4000,
          })
        }
      }, 1000)
    }
  } catch (e: any) {
    message.error(e?.message || '反馈提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.chat-bubble {
  display: flex;
  flex-direction: column;
  max-width: 80%;
}

.user-message {
  align-self: flex-end;
  align-items: flex-end;
}

.ai-message {
  align-self: flex-start;
  align-items: flex-start;
}

.bubble-content {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 15px;
  line-height: 1.5;
  word-break: break-word;
  -webkit-user-select: text;
  user-select: text;
}

.user-message .bubble-content {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.ai-message .bubble-content {
  background: #fff;
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
}

.streaming-raw {
  white-space: pre-wrap;
  font-family: inherit;
}

.streaming-cursor {
  display: inline-block;
  margin-left: 1px;
  animation: blink 1s steps(2) infinite;
  color: #1989fa;
}

@keyframes blink {
  50% { opacity: 0; }
}

.message-time {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
  padding: 0 4px;
}

.bubble-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding: 0 4px;
}

.feedback-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: transparent;
  border: 1px solid #e0e0e0;
  border-radius: 12px;
  font-size: 13px;
  color: #666;
  cursor: pointer;
  transition: all 0.15s ease;
}

.feedback-btn:hover:not(:disabled) {
  background: #f5f5f5;
  border-color: #1989fa;
  color: #1989fa;
}

.feedback-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.feedback-btn.active {
  background: #e8f3ff;
  border-color: #1989fa;
  color: #1989fa;
}

.feedback-btn .emoji {
  font-size: 14px;
}

.feedback-btn .rating-label {
  font-size: 12px;
}

.feedback-thanks {
  font-size: 11px;
  color: #999;
  margin-left: 4px;
}
</style>

<style>
/* Markdown 渲染样式（不使用 scoped，确保 v-html 内容也能应用） */
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
}

.markdown-body h1,
.markdown-body h2,
.markdown-body h3,
.markdown-body h4 {
  margin: 12px 0 8px;
  font-weight: 600;
  color: #323233;
}

.markdown-body h1 { font-size: 20px; }
.markdown-body h2 { font-size: 18px; border-bottom: 1px solid #e8e8e8; padding-bottom: 6px; }
.markdown-body h3 { font-size: 16px; }
.markdown-body h4 { font-size: 15px; }

.markdown-body p {
  margin: 6px 0;
}

.markdown-body ul,
.markdown-body ol {
  margin: 6px 0;
  padding-left: 20px;
}

.markdown-body li {
  margin: 4px 0;
  line-height: 1.6;
}

.markdown-body strong {
  font-weight: 600;
  color: #1a1a1a;
}

.markdown-body em {
  font-style: italic;
}

.markdown-body code {
  background: #e8e8e8;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: Menlo, Monaco, monospace;
}

.markdown-body pre {
  background: #f0f0f0;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-body pre code {
  background: none;
  padding: 0;
}

.markdown-body blockquote {
  border-left: 4px solid #1989fa;
  padding: 4px 12px;
  margin: 8px 0;
  color: #666;
  background: #f0f7ff;
  border-radius: 0 4px 4px 0;
}

.markdown-body a {
  color: #1989fa;
  text-decoration: none;
}

.markdown-body hr {
  border: none;
  border-top: 1px solid #e8e8e8;
  margin: 12px 0;
}

.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.markdown-body th,
.markdown-body td {
  border: 1px solid #e8e8e8;
  padding: 6px 10px;
  text-align: left;
  font-size: 13px;
}

.markdown-body th {
  background: #f5f5f5;
  font-weight: 600;
}
</style>
