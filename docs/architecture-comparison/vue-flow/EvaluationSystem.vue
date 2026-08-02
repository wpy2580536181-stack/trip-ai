<script setup lang="ts">
import { VueFlow, type Node, type Edge, type NodeProps, Position, Handle } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import { computed } from 'vue'

// ─── Custom Node: Group (2x2 grid of modes) ───────────────────────────────────
const GroupNode = (props: NodeProps) => {
  const cells = [
    { label: 'mock', color: '#d5e8d4', border: '#82b366' },
    { label: 'real', color: '#dae8fc', border: '#6c8ebf' },
    { label: 'multi-sample', color: '#e1d5e7', border: '#9673a6' },
    { label: 'report', color: '#ffe6cc', border: '#d79b00' },
  ]
  const border = computed(() => `${props.selected ? 3 : 2}px solid #333`)
  return () => (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Top} />
      <div
        style={{
          background: '#f5f5f5',
          border: border.value,
          borderRadius: '8px',
          padding: '8px',
          width: '220px',
        }}
      >
        <div
          style={{
            fontSize: '11px',
            fontWeight: 700,
            color: '#333',
            marginBottom: '6px',
            textAlign: 'center',
            letterSpacing: '0.5px',
          }}
        >
          4 MODES
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          {cells.map((c) => (
            <div
              key={c.label}
              style={{
                background: c.color,
                border: `1.5px solid ${c.border}`,
                borderRadius: '4px',
                padding: '8px 4px',
                textAlign: 'center',
                fontSize: '11px',
                fontWeight: 600,
                color: '#333',
              }}
            >
              {c.label}
            </div>
          ))}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

// ─── Custom Node: Default (rounded rectangle) ─────────────────────────────────
const ProcessNode = (props: NodeProps) => {
  const label = computed(() => (props.data as { label: string }).label)
  const border = computed(() => `${props.selected ? 3 : 2}px solid #6c8ebf`)
  return () => (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Left} />
      <Handle type="target" position={Position.Top} />
      <div
        style={{
          background: '#dae8fc',
          border: border.value,
          borderRadius: '8px',
          padding: '10px 14px',
          minWidth: '130px',
          maxWidth: '220px',
          textAlign: 'center',
          fontWeight: 600,
          fontSize: '12px',
          color: '#1a3a6c',
          whiteSpace: 'pre-line',
        }}
      >
        {label.value}
      </div>
      <Handle type="source" position={Position.Right} />
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

const nodeTypes = { group: GroupNode, process: ProcessNode }

const nodes: Node[] = [
  { id: 'fx', type: 'process', position: { x: 260, y: 0 }, data: { label: 'Fixtures\nfixtures/*.yaml +\nfixtures/generated/*.yaml' } },
  { id: 'en', type: 'process', position: { x: 260, y: 140 }, data: { label: 'CLI / API entry\n(eval / evalApi)' } },
  { id: 'run', type: 'process', position: { x: 260, y: 280 }, data: { label: 'Runner' } },
  { id: 'md', type: 'group', position: { x: 200, y: 420 }, data: {} },
  { id: 'ev', type: 'process', position: { x: 260, y: 620 }, data: { label: '13 Evaluators\nmust_contain_keywords · must_not ·\nregex · json_schema · ...' } },
  { id: 'llm', type: 'process', position: { x: 0, y: 620 }, data: { label: 'LLM\n(mock or real)' } },
  { id: 'out', type: 'process', position: { x: 260, y: 800 }, data: { label: 'Output\nJSON report · HTML report · score' } },
  { id: 'fb', type: 'process', position: { x: 260, y: 960 }, data: { label: 'Feedback Loop\nnegative feedback →\nfixtureConverter → new YAML' } },
]

const edges: Edge[] = [
  { id: 'fx-en', source: 'fx', target: 'en', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'en-run', source: 'en', target: 'run', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'run-md', source: 'run', target: 'md', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'md-ev', source: 'md', target: 'ev', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'ev-llm', source: 'ev', target: 'llm', label: '↔ invoke', style: { stroke: '#9673a6', strokeWidth: 2 }, animated: true },
  { id: 'ev-out', source: 'ev', target: 'out', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'out-fb', source: 'out', target: 'fb', label: 'negative', style: { stroke: '#d62728', strokeWidth: 2 } },
  { id: 'fb-fx', source: 'fb', target: 'fx', label: 'append', style: { stroke: '#82b366', strokeWidth: 2 } },
]
</script>

<template>
  <div style="width: 100%; height: 1100px">
    <VueFlow
      :nodes="nodes"
      :edges="edges"
      :node-types="nodeTypes"
      fit-view-on-init
    />
  </div>
</template>
