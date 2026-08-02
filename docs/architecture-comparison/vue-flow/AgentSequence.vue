<script setup lang="ts">
import { VueFlow, type Node, type Edge, type NodeProps, Position, Handle } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'

// ─── Custom Node: Actor (tall header bar) ─────────────────────────────────────
const ActorNode = (props: NodeProps) => {
  const data = computed(() => props.data as { label: string; color: string })
  return () => (
    <div
      :style="{
        background: data.value.color,
        color: '#fff',
        padding: '12px 8px',
        borderRadius: '6px',
        textAlign: 'center',
        fontWeight: 700,
        fontSize: '12px',
        width: '110px',
        minHeight: '50px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
      }"
    >
      {data.value.label}
    </div>
  )
}

const nodeTypes = { actor: ActorNode }

const ACTOR_X: Record<string, number> = { U: 60, FE: 220, BE: 380, AE: 540, L: 700, T: 860, DB: 1020 }

const nodes: Node[] = [
  { id: 'U', type: 'actor', position: { x: ACTOR_X.U!, y: 0 }, data: { label: 'User', color: '#6c8ebf' } },
  { id: 'FE', type: 'actor', position: { x: ACTOR_X.FE!, y: 0 }, data: { label: 'Frontend', color: '#6c8ebf' } },
  { id: 'BE', type: 'actor', position: { x: ACTOR_X.BE!, y: 0 }, data: { label: 'tripService', color: '#82b366' } },
  { id: 'AE', type: 'actor', position: { x: ACTOR_X.AE!, y: 0 }, data: { label: 'AgentEngine', color: '#82b366' } },
  { id: 'L', type: 'actor', position: { x: ACTOR_X.L!, y: 0 }, data: { label: 'LLM (DeepSeek)', color: '#9673a6' } },
  { id: 'T', type: 'actor', position: { x: ACTOR_X.T!, y: 0 }, data: { label: 'Tool', color: '#d6b656' } },
  { id: 'DB', type: 'actor', position: { x: ACTOR_X.DB!, y: 0 }, data: { label: 'MySQL', color: '#d79b00' } },
]

const edges: Edge[] = ['U', 'FE', 'BE', 'AE', 'L', 'T', 'DB'].map((id) => ({
  id: `life-${id}`,
  source: id,
  target: id,
  style: { stroke: '#999', strokeDasharray: '4 4' },
}))

interface Message {
  id: string
  num: number
  source: keyof typeof ACTOR_X
  target: keyof typeof ACTOR_X
  label: string
  dashed?: boolean
}

const messages: Message[] = [
  { id: 'm1', num: 1, source: 'U', target: 'FE', label: 'send message' },
  { id: 'm2', num: 2, source: 'FE', target: 'BE', label: 'POST /api/trip/chat (SSE)' },
  { id: 'm3', num: 3, source: 'BE', target: 'DB', label: 'pre-create empty assistant msg' },
  { id: 'm4', num: 4, source: 'BE', target: 'AE', label: 'chat({userId, messageId, signal, onEvent})' },
  { id: 'm5', num: 5, source: 'AE', target: 'L', label: 'invoke(messages + tools)' },
  { id: 'm6', num: 6, source: 'L', target: 'AE', label: 'tool_call {name, args}', dashed: true },
  { id: 'm7', num: 7, source: 'AE', target: 'T', label: 'execute(args)' },
  { id: 'm8', num: 8, source: 'T', target: 'AE', label: 'result', dashed: true },
  { id: 'm9', num: 9, source: 'AE', target: 'L', label: 'invoke(messages + tool result)' },
  { id: 'm10', num: 10, source: 'L', target: 'AE', label: 'content chunks', dashed: true },
  { id: 'm11', num: 11, source: 'AE', target: 'BE', label: 'on_tool_start / on_tool_end / on_chunk', dashed: true },
  { id: 'm12', num: 12, source: 'BE', target: 'FE', label: 'data: {type: "chunk"}', dashed: true },
  { id: 'm13', num: 13, source: 'BE', target: 'DB', label: 'persist assistant message' },
  { id: 'm14', num: 14, source: 'BE', target: 'FE', label: 'data: {type: "complete", reply, usage}' },
]

const startY = 100
const stepY = 36
</script>

<template>
  <div style="width: 100%; height: 700px; position: relative">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :nodes-draggable="false"
      fit-view-on-init
    />
    <svg
      style="position: absolute; inset: 0; pointer-events: none; width: 100%; height: 100%"
      viewBox="0 0 1200 700"
      preserveAspectRatio="none"
    >
      <defs>
        <marker id="arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#1976d2" />
        </marker>
        <marker id="arrow-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="#d62728" />
        </marker>
      </defs>
      <g v-for="(m, i) in messages" :key="m.id">
        <template v-if="ACTOR_X[m.source] !== undefined && ACTOR_X[m.target] !== undefined">
          <line
            :x1="ACTOR_X[m.source]! + 55"
            :y1="startY + i * stepY"
            :x2="ACTOR_X[m.target]! + 55"
            :y2="startY + i * stepY"
            :stroke="ACTOR_X[m.target]! < ACTOR_X[m.source]! ? '#d62728' : '#1976d2'"
            stroke-width="1.8"
            :stroke-dasharray="m.dashed ? '6 4' : undefined"
            :marker-end="`url(#${ACTOR_X[m.target]! < ACTOR_X[m.source]! ? 'arrow-red' : 'arrow-blue'})`"
          />
          <circle
            :cx="(ACTOR_X[m.source]! + 55 + ACTOR_X[m.target]! + 55) / 2"
            :cy="startY + i * stepY"
            r="10"
            fill="#fff"
            :stroke="ACTOR_X[m.target]! < ACTOR_X[m.source]! ? '#d62728' : '#1976d2'"
            stroke-width="1.5"
          />
          <text
            :x="(ACTOR_X[m.source]! + 55 + ACTOR_X[m.target]! + 55) / 2"
            :y="startY + i * stepY + 4"
            text-anchor="middle"
            font-size="10"
            font-weight="700"
            :fill="ACTOR_X[m.target]! < ACTOR_X[m.source]! ? '#d62728' : '#1976d2'"
          >
            {{ m.num }}
          </text>
          <text
            :x="(ACTOR_X[m.source]! + 55 + ACTOR_X[m.target]! + 55) / 2"
            :y="startY + i * stepY - 6"
            text-anchor="middle"
            font-size="10"
            fill="#333"
            style="paint-order: stroke; stroke: #fff; stroke-width: 3"
          >
            {{ m.label }}
          </text>
        </template>
      </g>
    </svg>
    <div
      style="position: absolute; bottom: 8px; right: 12px; background: rgba(255, 244, 196, 0.95); border: 1px solid #d6b656; border-radius: 4px; padding: 4px 10px; font-size: 11px; color: #6b4f00;"
    >
      ⚠ Vue Flow is not ideal for sequence diagrams — messages drawn via SVG overlay above the actor headers.
    </div>
  </div>
</template>
