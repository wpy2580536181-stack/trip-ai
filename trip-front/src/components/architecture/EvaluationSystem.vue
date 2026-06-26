<script setup lang="ts">
/**
 * 评估体系 (Evaluation System)
 *
 * 拓扑：fixtures → entry → runner → 4 modes → 13 evaluators → output → feedback loop
 * 闭环：output(negative) → feedback → fixtures（虚线）
 */
import { VueFlow, type Node, type Edge } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import ServiceNode from './nodes/ServiceNode.vue'
import GroupNode from './nodes/GroupNode.vue'
import CloudNode from './nodes/CloudNode.vue'
import DatabaseNode from './nodes/DatabaseNode.vue'

const nodeTypes = {
  service: ServiceNode,
  group: GroupNode,
  cloud: CloudNode,
  database: DatabaseNode,
}

const evaluators = [
  'must_contain_keywords',
  'must_not',
  'regex',
  'json_schema',
  'semantic_match',
  'tool_called',
  'latency',
  'token_count',
  'similarity',
  'contains_url',
  'language',
  'length',
  'cost',
]

const modes = ['mock', 'real', 'multi-sample', 'report']

const nodes: Node[] = [
  { id: 'fixtures', type: 'database', position: { x: 0, y: 20 }, data: { label: 'Fixtures (YAML)', sublabel: 'fixtures/**/*.yaml' } },
  { id: 'entry', type: 'service', position: { x: 220, y: 20 }, data: { label: 'CLI / API entry', sublabel: 'eval · evalApi', color: '#dae8fc' } },
  { id: 'runner', type: 'service', position: { x: 440, y: 20 }, data: { label: 'Runner', color: '#fff2cc' } },
  {
    id: 'modes',
    type: 'group',
    position: { x: 660, y: 0 },
    data: { label: '4 Modes', items: modes },
  },
  {
    id: 'evaluators',
    type: 'service',
    position: { x: 220, y: 200 },
    data: { label: `13 Evaluators`, sublabel: evaluators.slice(0, 4).join(' · ') + ' · ...', color: '#d5e8d4' },
  },
  { id: 'llm', type: 'cloud', position: { x: 0, y: 200 }, data: { label: 'LLM', sublabel: 'mock or real' } },
  { id: 'output', type: 'service', position: { x: 440, y: 200 }, data: { label: 'Output', sublabel: 'JSON · HTML · score', color: '#ffe6cc' } },
  { id: 'feedback', type: 'service', position: { x: 660, y: 200 }, data: { label: 'Feedback Loop', sublabel: 'fixtureConverter', color: '#e1d5e7' } },
]

const labelStyle = { fontSize: '10px', fill: '#333' }

const edges: Edge[] = [
  { id: 'e1', source: 'fixtures', target: 'entry', style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'e2', source: 'entry', target: 'runner', style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'e3', source: 'runner', target: 'modes', style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'e4', source: 'modes', target: 'evaluators', style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'e5', source: 'evaluators', target: 'llm', label: 'invoke', labelStyle, style: { stroke: '#999', strokeWidth: 1.5, strokeDasharray: '4 4' } },
  { id: 'e6', source: 'evaluators', target: 'output', style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'e7', source: 'output', target: 'feedback', label: 'negative', labelStyle, style: { stroke: '#d79b00', strokeWidth: 2 } },
  { id: 'e8', source: 'feedback', target: 'fixtures', label: 'append new fixture', labelStyle, style: { stroke: '#9673a6', strokeWidth: 2, strokeDasharray: '4 4' } },
]
</script>

<template>
  <div class="diagram-canvas">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      :default-viewport="{ x: 0, y: 0, zoom: 0.9 }"
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
