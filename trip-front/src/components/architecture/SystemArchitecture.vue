<script setup lang="ts">
import { VueFlow, type Node, type Edge } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import DatabaseNode from './nodes/DatabaseNode.vue'
import CloudNode from './nodes/CloudNode.vue'
import ServiceNode from './nodes/ServiceNode.vue'

const nodeTypes = { database: DatabaseNode, cloud: CloudNode, service: ServiceNode }

const nodes: Node[] = [
  // Row 0: Frontend
  { id: 'fe', type: 'service', position: { x: 360, y: 0 }, data: { label: 'Vue 3 + Vite + Pinia', sublabel: 'Element Plus', color: '#dae8fc' } },
  // Row 1: Backend
  { id: 'be', type: 'service', position: { x: 150, y: 140 }, data: { label: 'Express 5', sublabel: 'Prisma + Pino', color: '#d5e8d4' } },
  { id: 'agent', type: 'service', position: { x: 470, y: 140 }, data: { label: 'AgentEngine', sublabel: 'LangGraph', color: '#d5e8d4' } },
  // Row 2: Service layer
  { id: 'rag', type: 'service', position: { x: 150, y: 280 }, data: { label: 'KnowledgeService', sublabel: '3-path + RRF + rerank', color: '#fff2cc' } },
  { id: 'rewriter', type: 'service', position: { x: 15, y: 280 }, data: { label: 'QueryRewriter', sublabel: 'local keywords ~1ms', color: '#fff2cc' } },
  { id: 'reranker', type: 'service', position: { x: 295, y: 280 }, data: { label: 'Cross-Encoder', sublabel: 'bge-reranker-base', color: '#fff2cc' } },
  { id: 'mcp-client', type: 'service', position: { x: 470, y: 280 }, data: { label: 'Amap McpClient', sublabel: 'JSON-RPC + guard', color: '#e1d5e7' } },
  { id: 'img-fetcher', type: 'service', position: { x: 650, y: 280 }, data: { label: 'ImageFetcher', sublabel: 'batch + 30d LRU', color: '#e1d5e7' } },
  // Row 3: Data stores
  { id: 'mysql', type: 'database', position: { x: 15, y: 420 }, data: { label: 'MySQL 8', sublabel: 'Prisma ORM' } },
  { id: 'redis', type: 'database', position: { x: 145, y: 420 }, data: { label: 'Redis 7', sublabel: 'stream · rate limit' } },
  { id: 'chroma', type: 'database', position: { x: 275, y: 420 }, data: { label: 'Chroma', sublabel: '30k POI vectors' } },
  { id: 'mcp-proc', type: 'database', position: { x: 470, y: 420 }, data: { label: 'MCP stdio', sublabel: 'subprocess' } },
  // Row 4: External / Cloud
  { id: 'deepseek', type: 'cloud', position: { x: 145, y: 560 }, data: { label: 'DeepSeek', sublabel: 'deepseek-v4-flash' } },
  { id: 'bge', type: 'cloud', position: { x: 275, y: 560 }, data: { label: 'bge-small-zh', sublabel: 'Embedding 512d' } },
  { id: 'amap', type: 'cloud', position: { x: 470, y: 560 }, data: { label: 'Amap MCP', sublabel: '12 maps_* tools' } },
  { id: 'unsplash', type: 'cloud', position: { x: 650, y: 560 }, data: { label: 'Unsplash API', sublabel: 'fallback images' } },
]

const edges: Edge[] = [
  { id: 'e-fe-be', source: 'fe', target: 'be', label: 'HTTPS REST + SSE', animated: true, style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'e-be-agent', source: 'be', target: 'agent', style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'e-agent-rag', source: 'agent', target: 'rag', label: 'research(query, city)', style: { stroke: '#d79b00', strokeWidth: 1.5 } },
  { id: 'e-rag-rewriter', source: 'rag', target: 'rewriter', style: { stroke: '#999', strokeWidth: 1, strokeDasharray: '3 3' } },
  { id: 'e-rag-reranker', source: 'rag', target: 'reranker', style: { stroke: '#999', strokeWidth: 1, strokeDasharray: '3 3' } },
  { id: 'e-agent-mcp', source: 'agent', target: 'mcp-client', label: 'callTool', style: { stroke: '#9673a6', strokeWidth: 1.5 } },
  { id: 'e-mcp-proc', source: 'mcp-client', target: 'mcp-proc', style: { stroke: '#9673a6', strokeWidth: 1.5 } },
  { id: 'e-mcp-amap', source: 'mcp-proc', target: 'amap', label: 'tools/list · call', style: { stroke: '#9673a6', strokeWidth: 1.5 } },
  { id: 'e-be-img', source: 'be', target: 'img-fetcher', label: '行程完成→后端 batch', style: { stroke: '#d79b00', strokeWidth: 1.5, strokeDasharray: '5 3' } },
  { id: 'e-mysql', source: 'be', target: 'mysql', label: 'Prisma', style: { stroke: '#d79b00', strokeWidth: 1.5 } },
  { id: 'e-redis', source: 'be', target: 'redis', style: { stroke: '#d79b00', strokeWidth: 1.5 } },
  { id: 'e-chroma', source: 'rag', target: 'chroma', label: 'vector top-20', style: { stroke: '#d79b00', strokeWidth: 1.5 } },
  { id: 'e-mysql-rag', source: 'rag', target: 'mysql', label: 'LIKE + rating', style: { stroke: '#d79b00', strokeWidth: 1, strokeDasharray: '3 3' } },
  { id: 'e-deepseek', source: 'agent', target: 'deepseek', label: 'chat completion', style: { stroke: '#9673a6', strokeWidth: 1.5 } },
  { id: 'e-bge', source: 'rag', target: 'bge', label: 'embed query', style: { stroke: '#9673a6', strokeWidth: 1.5 } },
  { id: 'e-unsplash', source: 'img-fetcher', target: 'unsplash', label: 'fallback', style: { stroke: '#9673a6', strokeWidth: 1.5 } },
]
</script>

<template>
  <div class="diagram-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 0.85 }"
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
.vue-flow { background: #fafafa; }
</style>
