<script setup lang="ts">
/**
 * Agent 执行时序 (Agent Execution Sequence)
 *
 * 7 个 actor 横向排列，17 条消息箭头（实线=外部调用，虚线=内部事件）
 * 虚线：Backend/DB 预创建、AgentEngine → Backend 事件、Backend 异步任务
 */
import { VueFlow, type Node, type Edge, MarkerType } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import ActorNode from './nodes/ActorNode.vue'

const nodeTypes = { actor: ActorNode }

const actors = ['User', 'Frontend', 'Backend', 'AgentEngine', 'LLM', 'Tool', 'DB'] as const
const actorXSpacing = 170
const actorStartX = 40

const nodes: Node[] = actors.map((name, i) => ({
  id: name,
  type: 'actor',
  position: { x: actorStartX + i * actorXSpacing, y: 0 },
  data: { label: name },
}))

type Message = readonly [string, string, string, boolean?]

const messages: readonly Message[] = [
  ['User', 'Frontend', 'send message'],
  ['Frontend', 'Backend', 'POST /api/trip/chat (SSE)'],
  ['Backend', 'DB', 'pre-create empty assistant msg', true],
  ['Backend', 'AgentEngine', 'chat({userId, messageId, signal, onEvent})'],
  ['AgentEngine', 'LLM', 'invoke (messages + tools)'],
  ['LLM', 'AgentEngine', 'tool_call {name, args}'],
  ['AgentEngine', 'Tool', 'execute(args)'],
  ['Tool', 'AgentEngine', 'result'],
  ['AgentEngine', 'Backend', 'on_tool_start / on_tool_end', true],
  ['AgentEngine', 'LLM', 'invoke (messages + tool result)'],
  ['LLM', 'AgentEngine', 'content chunks'],
  ['AgentEngine', 'Backend', 'on_chunk (SSE)', true],
  ['Backend', 'Frontend', 'SSE data: {type: chunk}'],
  ['Backend', 'DB', 'persist assistant message', true],
  ['AgentEngine', 'Backend', 'on_complete (with usage)', true],
  ['Backend', 'Frontend', 'SSE data: {type: complete, reply, usage}'],
  ['Backend', 'Backend', 'compressConversation (async)', true],
] as const

const edges: Edge[] = messages.map(([source, target, label, isInternal], i) => {
  const stroke = isInternal ? '#82b366' : '#1976d2'
  return {
    id: `m${i + 1}`,
    source,
    target,
    label: `${i + 1}. ${label}`,
    labelStyle: { fontSize: '10px', fill: '#333' },
    labelBgPadding: [4, 2],
    labelBgStyle: { fill: '#fff', fillOpacity: 0.85 },
    style: {
      stroke,
      strokeWidth: 1.5,
      strokeDasharray: isInternal ? '4 4' : undefined,
    },
    markerEnd: { type: MarkerType.ArrowClosed, color: stroke, width: 14, height: 14 },
    type: 'straight',
  }
})
</script>

<template>
  <div class="diagram-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 0.7 }"
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
.vue-flow {
  background: #fafafa;
}
</style>
