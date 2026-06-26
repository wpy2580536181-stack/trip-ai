<script setup lang="ts">
/**
 * 系统架构图 (System Architecture)
 *
 * 拓扑：Frontend → Backend → {MySQL, Redis, Chroma, DeepSeek, bge}
 * 颜色：前端蓝、后端绿、DB 橙、云紫
 */
import { VueFlow, type Node, type Edge } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import DatabaseNode from './nodes/DatabaseNode.vue'
import CloudNode from './nodes/CloudNode.vue'
import ServiceNode from './nodes/ServiceNode.vue'

const nodeTypes = { database: DatabaseNode, cloud: CloudNode, service: ServiceNode }

const nodes: Node[] = [
  {
    id: 'frontend',
    type: 'service',
    position: { x: 280, y: 0 },
    data: { label: 'Vue 3 + Vite + Pinia', sublabel: 'Frontend', color: '#dae8fc' },
  },
  {
    id: 'backend',
    type: 'service',
    position: { x: 280, y: 140 },
    data: { label: 'Express 5', sublabel: 'Prisma + Pino', color: '#d5e8d4' },
  },
  {
    id: 'mysql',
    type: 'database',
    position: { x: 10, y: 300 },
    data: { label: 'MySQL 8', sublabel: 'Prisma ORM' },
  },
  {
    id: 'redis',
    type: 'database',
    position: { x: 160, y: 300 },
    data: { label: 'Redis 7', sublabel: 'streamStore · rate limit' },
  },
  {
    id: 'chroma',
    type: 'database',
    position: { x: 310, y: 300 },
    data: { label: 'Chroma', sublabel: 'Vector DB' },
  },
  {
    id: 'deepseek',
    type: 'cloud',
    position: { x: 460, y: 300 },
    data: { label: 'DeepSeek', sublabel: 'deepseek-v4-flash' },
  },
  {
    id: 'bge',
    type: 'cloud',
    position: { x: 620, y: 300 },
    data: { label: 'bge-small-zh', sublabel: 'Embedding' },
  },
]

const edges: Edge[] = [
  {
    id: 'e-fe-be',
    source: 'frontend',
    target: 'backend',
    label: 'HTTPS REST + SSE',
    animated: true,
    style: { stroke: '#1976d2', strokeWidth: 2 },
  },
  { id: 'e-be-mysql', source: 'backend', target: 'mysql', label: 'Prisma', style: { stroke: '#d79b00', strokeWidth: 2 } },
  { id: 'e-be-redis', source: 'backend', target: 'redis', label: 'ioredis', style: { stroke: '#d79b00', strokeWidth: 2 } },
  { id: 'e-be-chroma', source: 'backend', target: 'chroma', label: 'vector search', style: { stroke: '#d79b00', strokeWidth: 2 } },
  { id: 'e-be-deepseek', source: 'backend', target: 'deepseek', label: 'chat completion', style: { stroke: '#9673a6', strokeWidth: 2 } },
  { id: 'e-be-bge', source: 'backend', target: 'bge', label: 'embedding', style: { stroke: '#9673a6', strokeWidth: 2 } },
]
</script>

<template>
  <div class="diagram-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 0.95 }"
      fit-view-on-init
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
