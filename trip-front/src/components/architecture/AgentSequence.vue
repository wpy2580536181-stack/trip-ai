<script setup lang="ts">
import { VueFlow, type Node, type Edge, MarkerType } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import ActorNode from './nodes/ActorNode.vue'

const nodeTypes = { actor: ActorNode }

const actors = ['User', 'Frontend', 'Backend', 'AgentEngine', 'RAG', 'LLM', 'MCP', 'DB', 'IMG'] as const
const actorXSpacing = 170
const actorStartX = 20

const nodes: Node[] = actors.map((name, i) => ({
  id: name,
  type: 'actor',
  position: { x: actorStartX + i * actorXSpacing, y: 0 },
  data: { label: name },
}))

type Message = readonly [string, string, string, boolean?]

const messages: readonly Message[] = [
  // 1-3: User sends message
  ['User', 'Frontend', 'send message'],
  ['Frontend', 'Backend', 'POST /api/trip/chat (SSE)'],
  ['Backend', 'DB', 'pre-create empty msg', true],
  ['Backend', 'AgentEngine', 'chat({…signal, onEvent})'],
  // 5-8: Research phase → RAG
  ['AgentEngine', 'RAG', 'research(query, city)'],
  ['RAG', 'RAG', 'rewriteQuery → 3-path recall → RRF → rerank', true],
  ['RAG', 'DB', 'vector + keyword + rating'],
  ['RAG', 'AgentEngine', 'top-5 POI results'],
  // 9-12: LLM tool call loop
  ['AgentEngine', 'LLM', 'invoke(messages + tools)'],
  ['LLM', 'AgentEngine', 'tool_call maps_*'],
  ['AgentEngine', 'MCP', 'callTool(name, args)'],
  ['MCP', 'AgentEngine', 'result'],
  // 13-16: LLM streaming
  ['AgentEngine', 'LLM', 'invoke(messages + result)'],
  ['LLM', 'AgentEngine', 'content chunks'],
  ['AgentEngine', 'Backend', 'on_chunk / on_tool_end', true],
  ['Backend', 'Frontend', 'SSE data: {type: chunk}'],
  // 17-19: Complete
  ['AgentEngine', 'Backend', 'on_complete (with usage)', true],
  ['Backend', 'DB', 'persist assistant message', true],
  ['Backend', 'Frontend', 'SSE data: {type: complete}'],
  // 20-21: Async image fetch
  ['Backend', 'IMG', 'fetchImages(itinerary)', true],
  ['IMG', 'DB', 'update trip.itinerary', true],
] as const

const labelIndices = new Set([3, 4, 8, 10, 12, 15])

const edges: Edge[] = messages.map(([source, target, label, isInternal], i) => {
  const stroke = isInternal ? '#82b366' : '#1976d2'
  return {
    id: `m${i + 1}`,
    source,
    target,
    label: labelIndices.has(i) ? `${i + 1}. ${label}` : undefined,
    labelStyle: { fontSize: '9px', fill: '#333' },
    labelBgPadding: [3, 2],
    labelBgStyle: { fill: '#fff', fillOpacity: 0.85 },
    style: {
      stroke,
      strokeWidth: 1.5,
      strokeDasharray: isInternal ? '4 4' : undefined,
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 14, height: 14 },
    type: 'smoothstep',
  }
})
</script>

<template>
  <div class="diagram-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 0.65 }"
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
