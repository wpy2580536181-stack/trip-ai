<script setup lang="ts">
/**
 * 上下文管理数据流 (Context Management Data Flow)
 *
 * 横向流程：message → history → counter → budget(决策) → 三分支 → compressor → LLM
 * 三分支：within（绿）、near（黄）、over（红）
 */
import { VueFlow, type Node, type Edge } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import ServiceNode from './nodes/ServiceNode.vue'
import DatabaseNode from './nodes/DatabaseNode.vue'
import DecisionNode from './nodes/DecisionNode.vue'
import CloudNode from './nodes/CloudNode.vue'

const nodeTypes = {
  service: ServiceNode,
  database: DatabaseNode,
  decision: DecisionNode,
  cloud: CloudNode,
}

const nodes: Node[] = [
  { id: 'msg', type: 'service', position: { x: 0, y: 100 }, data: { label: '用户消息', color: '#dae8fc' } },
  { id: 'history', type: 'database', position: { x: 180, y: 100 }, data: { label: '消息历史', sublabel: 'MySQL' } },
  { id: 'counter', type: 'service', position: { x: 360, y: 100 }, data: { label: 'Token 计数', sublabel: '当前用量', color: '#fff2cc' } },
  { id: 'budget', type: 'decision', position: { x: 540, y: 80 }, data: { label: 'Token 预算?', sublabel: 'HISTORY_MAX=8000' } },
  { id: 'keep', type: 'service', position: { x: 740, y: -20 }, data: { label: '全部保留', sublabel: '预算充足', color: '#d5e8d4' } },
  { id: 'summarize', type: 'service', position: { x: 740, y: 100 }, data: { label: '摘要旧消息', sublabel: '接近上限', color: '#ffe6cc' } },
  { id: 'compress', type: 'service', position: { x: 740, y: 220 }, data: { label: '压缩路径', sublabel: '超出上限', color: '#f8cecc' } },
  { id: 'compressor', type: 'service', position: { x: 940, y: 100 }, data: { label: 'compressConversation', color: '#fff2cc' } },
  { id: 'summary-cache', type: 'database', position: { x: 940, y: 240 }, data: { label: '摘要缓存', sublabel: '内存' } },
  { id: 'llm-call', type: 'cloud', position: { x: 1140, y: 100 }, data: { label: 'LLM 调用', sublabel: '压缩后上下文' } },
]

const labelStyle = { fontSize: '10px', fill: '#333' }

const edges: Edge[] = [
  { id: 'e1', source: 'msg', target: 'history', style: { stroke: '#999', strokeWidth: 1.5 } },
  { id: 'e2', source: 'history', target: 'counter', style: { stroke: '#999', strokeWidth: 1.5 } },
  { id: 'e3', source: 'counter', target: 'budget', style: { stroke: '#999', strokeWidth: 1.5 } },
  { id: 'e4', source: 'budget', sourceHandle: 'yes', target: 'keep', label: '充足', labelStyle, style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'e5', source: 'budget', target: 'summarize', label: '接近', labelStyle, style: { stroke: '#d6b656', strokeWidth: 2 } },
  { id: 'e6', source: 'budget', sourceHandle: 'no', target: 'compress', label: '超出', labelStyle, style: { stroke: '#b85450', strokeWidth: 2 } },
  { id: 'e7', source: 'keep', target: 'compressor', style: { stroke: '#82b366', strokeDasharray: '4 4' } },
  { id: 'e8', source: 'summarize', target: 'compressor', style: { stroke: '#d6b656', strokeWidth: 2 } },
  { id: 'e9', source: 'compress', target: 'compressor', style: { stroke: '#b85450', strokeWidth: 2 } },
  { id: 'e10', source: 'compressor', target: 'summary-cache', style: { stroke: '#999', strokeDasharray: '4 4' } },
  { id: 'e11', source: 'compressor', target: 'llm-call', style: { stroke: '#1976d2', strokeWidth: 2 }, animated: true },
]
</script>

<template>
  <div class="diagram-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 0.8 }"
      fit-view-on-init
      :nodes-draggable="false"
    />
  </div>
</template>

<style scoped>
.diagram-canvas {
  width: 100%;
  height: 100%;
  background: #fafafa;
}
</style>

<style>
.vue-flow {
  background: #fafafa;
}
</style>
