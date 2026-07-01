<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

type MsgKind = 'sync' | 'internal' | 'async'

interface Actor {
  id: string
  label: string
  sublabel: string
  color: string
  border: string
}

interface Message {
  from: string
  to: string
  label: string
  kind: MsgKind
}

interface Phase {
  label: string
  color: string
  start: number
  end: number
}

const ACTOR_W = 116
const ACTOR_H = 52
const ACTOR_GAP = 56
const FIRST_MSG_Y = 130
const MSG_ROW_H = 58
const PADDING_X = 32
const PADDING_Y = 28

const actors: readonly Actor[] = [
  { id: 'User', label: 'User', sublabel: '游客', color: '#f5f5f5', border: '#9e9e9e' },
  { id: 'Frontend', label: 'Frontend', sublabel: 'Vue 3 + SSE', color: '#dae8fc', border: '#6c8ebf' },
  { id: 'Backend', label: 'Backend', sublabel: 'Express + Prisma', color: '#d5e8d4', border: '#82b366' },
  { id: 'AgentEngine', label: 'AgentEngine', sublabel: 'LangGraph', color: '#d5e8d4', border: '#82b366' },
  { id: 'RAG', label: 'RAG', sublabel: '3-path + RRF', color: '#fff2cc', border: '#d6b656' },
  { id: 'LLM', label: 'LLM', sublabel: 'DeepSeek', color: '#e1d5e7', border: '#9673a6' },
  { id: 'MCP', label: 'MCP', sublabel: 'Amap stdio', color: '#e1d5e7', border: '#9673a6' },
  { id: 'DB', label: 'DB', sublabel: 'MySQL · Redis · Chroma', color: '#ffe6cc', border: '#d79b00' },
  { id: 'IMG', label: 'IMG', sublabel: 'ImageFetcher', color: '#e1d5e7', border: '#9673a6' },
]

const messages: readonly Message[] = [
  { from: 'User', to: 'Frontend', label: '发送消息', kind: 'sync' },
  { from: 'Frontend', to: 'Backend', label: 'POST /api/trip/chat', kind: 'sync' },
  { from: 'Backend', to: 'DB', label: '预创建空消息', kind: 'internal' },
  { from: 'Backend', to: 'AgentEngine', label: 'chat(signal, onEvent)', kind: 'sync' },
  { from: 'AgentEngine', to: 'RAG', label: 'research(query, city)', kind: 'sync' },
  { from: 'AgentEngine', to: 'LLM', label: 'invoke(messages + tools)', kind: 'sync' },
  { from: 'LLM', to: 'AgentEngine', label: 'tool_call: maps_weather', kind: 'async' },
  { from: 'AgentEngine', to: 'MCP', label: 'callTool(maps_weather)', kind: 'sync' },
  { from: 'MCP', to: 'AgentEngine', label: '返回结果', kind: 'async' },
  { from: 'AgentEngine', to: 'LLM', label: 'invoke(带 tool result)', kind: 'sync' },
  { from: 'LLM', to: 'AgentEngine', label: '流式 content chunk', kind: 'async' },
  { from: 'AgentEngine', to: 'Backend', label: 'on_chunk', kind: 'internal' },
  { from: 'Backend', to: 'Frontend', label: 'SSE chunk', kind: 'async' },
  { from: 'AgentEngine', to: 'Backend', label: 'on_complete', kind: 'internal' },
  { from: 'Backend', to: 'DB', label: '持久化消息', kind: 'internal' },
  { from: 'Backend', to: 'Frontend', label: 'SSE complete', kind: 'async' },
  { from: 'Backend', to: 'IMG', label: 'fetchImages', kind: 'internal' },
]

const phases: readonly Phase[] = [
  { label: '1 · 请求接入', color: '#e3f2fd', start: 0, end: 4 },
  { label: '2 · 上下文检索', color: '#fff8e1', start: 4, end: 5 },
  { label: '3 · LLM 推理 + 工具调用', color: '#f3e5f5', start: 5, end: 10 },
  { label: '4 · 流式输出', color: '#e8f5e9', start: 10, end: 13 },
  { label: '5 · 持久化', color: '#fbe9e7', start: 13, end: 16 },
  { label: '6 · 图片获取', color: '#ede7f6', start: 16, end: 17 },
]

function styleOf(kind: MsgKind) {
  switch (kind) {
    case 'sync':
      return { stroke: '#1565c0', dash: undefined, arrow: 'url(#arrow-filled)', labelBg: '#e8f4fd' }
    case 'internal':
      return { stroke: '#558b2f', dash: '6 4', arrow: 'url(#arrow-filled)', labelBg: '#f1f8e9' }
    case 'async':
      return { stroke: '#6a1b9a', dash: '5 4', arrow: 'url(#arrow-open)', labelBg: '#f3e5f5' }
  }
}

function actorCenterX(i: number): number {
  return PADDING_X + ACTOR_W / 2 + i * (ACTOR_W + ACTOR_GAP)
}
function msgCenterY(i: number): number {
  return FIRST_MSG_Y + i * MSG_ROW_H
}
function actorIndex(id: string): number {
  return actors.findIndex((a) => a.id === id)
}

const totalW = computed(
  () => PADDING_X + actors.length * ACTOR_W + (actors.length - 1) * ACTOR_GAP + PADDING_X,
)
const totalH = computed(() => msgCenterY(messages.length - 1) + MSG_ROW_H + PADDING_Y)

function phaseRect(p: Phase) {
  const x1 = PADDING_X - 14
  const x2 = totalW.value - PADDING_X + 14
  const y1 = msgCenterY(p.start) - MSG_ROW_H / 2 - 4
  const y2 = msgCenterY(p.end - 1) + MSG_ROW_H / 2 + 4
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 }
}

function labelTextWidth(s: string): number {
  let w = 0
  for (const ch of s) w += /[\u4e00-\u9fff，。：；]/.test(ch) ? 12 : 6.5
  return w
}

function labelBox(m: Message, i: number) {
  const fromX = actorCenterX(actorIndex(m.from))
  const toX = actorCenterX(actorIndex(m.to))
  const midX = (fromX + toX) / 2
  const text = `${i + 1}. ${m.label}`
  const w = labelTextWidth(text) + 14
  return { x: midX - w / 2, y: msgCenterY(i) - 32, w, h: 20, text }
}

const containerRef = ref<HTMLDivElement>()
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const dragging = ref(false)
const dragStart = { x: 0, y: 0, panX: 0, panY: 0 }

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  const newZoom = Math.min(3, Math.max(0.3, zoom.value * factor))
  const el = containerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const cx = (mx - panX.value) / zoom.value
  const cy = (my - panY.value) / zoom.value
  zoom.value = newZoom
  panX.value = mx - cx * newZoom
  panY.value = my - cy * newZoom
}

function onMouseDown(e: MouseEvent) {
  if ((e.target as HTMLElement).closest('.no-pan')) return
  dragging.value = true
  dragStart.x = e.clientX
  dragStart.y = e.clientY
  dragStart.panX = panX.value
  dragStart.panY = panY.value
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}
function onMouseMove(e: MouseEvent) {
  if (!dragging.value) return
  panX.value = dragStart.panX + (e.clientX - dragStart.x)
  panY.value = dragStart.panY + (e.clientY - dragStart.y)
}
function onMouseUp() {
  dragging.value = false
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

function fitToContainer() {
  const el = containerRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  const scaleX = rect.width / totalW.value
  const scaleY = rect.height / totalH.value
  const fitZoom = Math.min(scaleX, scaleY) * 0.94
  zoom.value = Math.min(1.4, fitZoom)
  panX.value = (rect.width - totalW.value * zoom.value) / 2
  panY.value = (rect.height - totalH.value * zoom.value) / 2
}

function reset() {
  fitToContainer()
}

onMounted(() => {
  requestAnimationFrame(fitToContainer)
  window.addEventListener('resize', fitToContainer)
})
</script>

<template>
  <div
    ref="containerRef"
    class="diagram-canvas"
    :class="{ dragging }"
    @wheel.passive="onWheel"
    @mousedown="onMouseDown"
    @dblclick="reset"
  >
    <svg
      class="diagram-svg"
      :width="totalW"
      :height="totalH"
      :viewBox="`0 0 ${totalW} ${totalH}`"
    >
      <defs>
        <marker
          id="arrow-filled"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="8"
          markerHeight="8"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" />
        </marker>
        <marker
          id="arrow-open"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="10"
          markerHeight="10"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10" fill="none" stroke-width="1.5" />
        </marker>
        <pattern id="lifeline-dash" x="0" y="0" width="6" height="6" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="6" stroke="#bdbdbd" stroke-width="1" />
        </pattern>
      </defs>

      <g :transform="`translate(${panX}, ${panY}) scale(${zoom})`">
        <!-- Phase 背景 -->
        <g class="phases">
          <g v-for="(p, pi) in phases" :key="`ph-${pi}`">
            <rect
              v-if="pi === 0 || phases[pi - 1].color !== p.color"
              :x="phaseRect(p).x"
              :y="phaseRect(p).y"
              :width="phaseRect(p).w"
              :height="phaseRect(p).h"
              :fill="p.color"
              :fill-opacity="0.55"
              rx="6"
            />
            <text
              :x="phaseRect(p).x + 10"
              :y="phaseRect(p).y + 16"
              font-size="11"
              font-weight="600"
              fill="#455a64"
            >
              {{ p.label }}
            </text>
          </g>
        </g>

        <!-- Lifelines -->
        <g class="lifelines">
          <line
            v-for="(a, i) in actors"
            :key="`ll-${a.id}`"
            :x1="actorCenterX(i)"
            :y1="ACTOR_H + 6"
            :x2="actorCenterX(i)"
            :y2="totalH - 10"
            stroke="#bdbdbd"
            stroke-width="1"
            stroke-dasharray="4 4"
          />
        </g>

        <!-- Actor 头 -->
        <g class="actors">
          <g v-for="(a, i) in actors" :key="a.id" class="actor-head no-pan" :transform="`translate(${actorCenterX(i) - ACTOR_W / 2}, 0)`">
            <rect
              :width="ACTOR_W"
              :height="ACTOR_H"
              :fill="a.color"
              :stroke="a.border"
              stroke-width="1.5"
              rx="6"
            />
            <text
              :x="ACTOR_W / 2"
              y="22"
              text-anchor="middle"
              font-size="13"
              font-weight="600"
              fill="#263238"
            >
              {{ a.label }}
            </text>
            <text
              :x="ACTOR_W / 2"
              y="38"
              text-anchor="middle"
              font-size="10"
              fill="#546e7a"
            >
              {{ a.sublabel }}
            </text>
          </g>
        </g>

        <!-- Messages -->
        <g class="messages">
          <g v-for="(m, i) in messages" :key="`m-${i}`">
            <line
              :x1="actorCenterX(actorIndex(m.from))"
              :y1="msgCenterY(i)"
              :x2="actorCenterX(actorIndex(m.to))"
              :y2="msgCenterY(i)"
              :stroke="styleOf(m.kind).stroke"
              :stroke-dasharray="styleOf(m.kind).dash"
              :marker-end="styleOf(m.kind).arrow"
              stroke-width="1.6"
            />
            <rect
              :x="labelBox(m, i).x"
              :y="labelBox(m, i).y"
              :width="labelBox(m, i).w"
              :height="labelBox(m, i).h"
              :fill="styleOf(m.kind).labelBg"
              :stroke="styleOf(m.kind).stroke"
              stroke-opacity="0.25"
              stroke-width="0.5"
              rx="3"
              class="no-pan"
            />
            <text
              :x="labelBox(m, i).x + labelBox(m, i).w / 2"
              :y="labelBox(m, i).y + 14"
              text-anchor="middle"
              font-size="11"
              fill="#37474f"
              class="no-pan"
            >
              {{ labelBox(m, i).text }}
            </text>
          </g>
        </g>
      </g>
    </svg>

    <div class="hint no-pan" @click="reset">双击或点击此处重置视图</div>
  </div>
</template>

<style scoped>
.diagram-canvas {
  width: 100%;
  height: 100%;
  background: #fafafa;
  overflow: hidden;
  position: relative;
  cursor: grab;
  user-select: none;
}
.diagram-canvas.dragging {
  cursor: grabbing;
}
.diagram-svg {
  display: block;
}
.hint {
  position: absolute;
  right: 12px;
  bottom: 10px;
  font-size: 11px;
  color: #90a4ae;
  background: rgba(255, 255, 255, 0.85);
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid #e0e0e0;
}
.hint:hover {
  color: #1976d2;
  border-color: #1976d2;
}
</style>
