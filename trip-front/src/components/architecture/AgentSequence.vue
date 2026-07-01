<script setup lang="ts">
import { VueFlow, type Node, type Edge, MarkerType } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import ActorNode from './nodes/ActorNode.vue'

const nodeTypes = { actor: ActorNode }

const actors = ['User', 'Frontend', 'Backend', 'AgentEngine', 'RAG', 'LLM', 'MCP', 'DB', 'IMG'] as const
const actorX = 155
const actorStartX = 40

const nodes: Node[] = actors.map((name, i) => ({
  id: name,
  type: 'actor',
  position: { x: actorStartX + i * actorX, y: 0 },
  data: { label: name },
}))

type Msg = readonly [string, string, string, boolean?]

const messages: readonly Msg[] = [
  ['User', 'Frontend', '发送消息'],
  ['Frontend', 'Backend', 'POST /api/trip/chat'],
  ['Backend', 'DB', '预创建空消息', true],
  ['Backend', 'AgentEngine', 'chat(signal, onEvent)'],
  ['AgentEngine', 'RAG', 'research(query, city)'],
  ['AgentEngine', 'LLM', 'invoke(messages + tools)'],
  ['LLM', 'AgentEngine', 'tool_call maps_weather'],
  ['AgentEngine', 'MCP', 'callTool'],
  ['MCP', 'AgentEngine', '返回结果'],
  ['AgentEngine', 'LLM', 'invoke(带 tool result)'],
  ['LLM', 'AgentEngine', '流式 content chunk'],
  ['AgentEngine', 'Backend', 'on_chunk', true],
  ['Backend', 'Frontend', 'SSE chunk'],
  ['AgentEngine', 'Backend', 'on_complete', true],
  ['Backend', 'DB', '持久化消息', true],
  ['Backend', 'Frontend', 'SSE complete'],
  ['Backend', 'IMG', 'fetchImages', true],
]

const edges: Edge[] = messages.map(([source, target, label, isInternal], i) => {
  const stroke = isInternal ? '#82b366' : '#1976d2'
  return {
    id: `m${i + 1}`,
    source,
    target,
    label: `${i + 1}`,
    labelStyle: { fontSize: '9px', fill: '#333' },
    labelBgPadding: [6, 2],
    labelBgStyle: { fill: isInternal ? '#f0faf0' : '#e8f4fd', fillOpacity: 0.9 },
    style: { stroke, strokeWidth: 1.5, strokeDasharray: isInternal ? '4 4' : undefined },
    markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 12, height: 12 },
    type: 'default',
  }
})
</script>

<template>
  <div class="diagram-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      fit-view-on-init
      :nodes-draggable="false"
      :nodes-connectable="false"
      :elements-selectable="false"
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
.vue-flow { background: #fafafa; }
</style>
