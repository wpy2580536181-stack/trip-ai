<script setup lang="ts">
import { VueFlow, type Node, type Edge, MarkerType } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import ServiceNode from './nodes/ServiceNode.vue'
import DatabaseNode from './nodes/DatabaseNode.vue'
import CloudNode from './nodes/CloudNode.vue'
import DecisionNode from './nodes/DecisionNode.vue'

const nodeTypes = {
  service: ServiceNode,
  database: DatabaseNode,
  cloud: CloudNode,
  decision: DecisionNode,
}

const nodes: Node[] = [
  { id: 'query', type: 'service', position: { x: 10, y: 20 }, data: { label: '用户查询', sublabel: '"看夜景最好的地方"', color: '#dae8fc' } },
  { id: 'rewriter', type: 'service', position: { x: 10, y: 150 }, data: { label: 'QueryRewriter', sublabel: '本地关键词提取 ~1ms', color: '#fff2cc' } },
  { id: 'rewritten', type: 'service', position: { x: 10, y: 280 }, data: { label: '改写后', sublabel: '"广州 夜景 珠江"', color: '#d5e8d4' } },
  // three paths
  { id: 'path1', type: 'service', position: { x: 200, y: 120 }, data: { label: 'Chroma 向量检索', sublabel: 'top-20 语义相似', color: '#ffe6cc' } },
  { id: 'path2', type: 'service', position: { x: 200, y: 230 }, data: { label: 'MySQL LIKE 关键词', sublabel: 'top-10 精确匹配', color: '#ffe6cc' } },
  { id: 'path3', type: 'service', position: { x: 200, y: 340 }, data: { label: 'MySQL rating', sublabel: 'top-10 热度兜底', color: '#ffe6cc' } },
  // RRF
  { id: 'rrf', type: 'service', position: { x: 410, y: 220 }, data: { label: 'RRF 融合', sublabel: '3 路去重 → top-20', color: '#d5e8d4' } },
  // Decision
  { id: 'decision', type: 'decision', position: { x: 590, y: 200 }, data: { label: '跳过重排?', sublabel: 'top-1 rrfScore>0.15' } },
  // Branches
  { id: 'skip', type: 'service', position: { x: 770, y: 120 }, data: { label: '直接 top-5', sublabel: '置信度足够', color: '#d5e8d4' } },
  { id: 'rerank', type: 'cloud', position: { x: 770, y: 280 }, data: { label: 'Cross-Encoder', sublabel: 'bge-reranker-base' } },
  // Result
  { id: 'result', type: 'service', position: { x: 960, y: 200 }, data: { label: '最终输出', sublabel: '5 条 POI', color: '#dae8fc' } },
]

const edges: Edge[] = [
  { id: 'e1', source: 'query', target: 'rewriter', style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'e2', source: 'rewriter', target: 'rewritten', style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'e3', source: 'rewritten', target: 'path1', style: { stroke: '#1976d2', strokeWidth: 1.5 } },
  { id: 'e4', source: 'rewritten', target: 'path2', style: { stroke: '#1976d2', strokeWidth: 1.5 } },
  { id: 'e5', source: 'rewritten', target: 'path3', style: { stroke: '#1976d2', strokeWidth: 1.5 } },
  { id: 'e6', source: 'path1', target: 'rrf', style: { stroke: '#d79b00', strokeWidth: 1.5 } },
  { id: 'e7', source: 'path2', target: 'rrf', style: { stroke: '#d79b00', strokeWidth: 1.5 } },
  { id: 'e8', source: 'path3', target: 'rrf', style: { stroke: '#d79b00', strokeWidth: 1.5 } },
  { id: 'e9', source: 'rrf', target: 'decision', style: { stroke: '#1976d2', strokeWidth: 2 }, animated: true },
  // Yes = skip rerank
  { id: 'e10', source: 'decision', sourceHandle: 'yes', target: 'skip', label: '是', style: { stroke: '#82b366', strokeWidth: 2 } },
  // No = do rerank
  { id: 'e11', source: 'decision', sourceHandle: 'no', target: 'rerank', label: '否', style: { stroke: '#b85450', strokeWidth: 2 } },
  // Both to result
  { id: 'e12', source: 'skip', target: 'result', style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'e13', source: 'rerank', target: 'result', style: { stroke: '#9673a6', strokeWidth: 2 } },
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
.vue-flow { background: #fafafa; }
</style>
