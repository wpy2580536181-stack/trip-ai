<template>
  <div class="chat-bubble" :class="messageClass">
    <div class="bubble-content">
      <div class="message-text" v-if="message.role === 'user'">{{ message.content }}</div>
      <div class="message-text ai-message markdown-body" v-else v-html="renderedContent"></div>
    </div>
    <div class="message-time" v-if="showTime">{{ formatTime }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

marked.setOptions({
  breaks: true,
  gfm: true,
})

interface Message {
  role: 'user' | 'ai'
  content: string
  timestamp?: string
}

const props = defineProps<{
  message: Message
}>()

const messageClass = computed(() => {
  return props.message.role === 'user' ? 'user-message' : 'ai-message'
})

const renderedContent = computed(() => {
  if (!props.message.content) return ''
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
  background: #1989fa;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.ai-message .bubble-content {
  background: #f5f5f5;
  color: #323233;
  border-bottom-left-radius: 4px;
}

.message-time {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
  padding: 0 4px;
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