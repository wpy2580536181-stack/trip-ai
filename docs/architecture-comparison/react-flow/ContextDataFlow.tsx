import { ReactFlow, Handle, Position, type Node, type Edge, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

// ─── Custom Node: Decision (diamond) ──────────────────────────────────────────
function DecisionNode({ data, selected }: NodeProps) {
  const label = (data as { label: string }).label
  return (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Left} />
      <svg width="180" height="100" viewBox="0 0 180 100">
        <polygon
          points="90,5 175,50 90,95 5,50"
          fill="#fff2cc"
          stroke="#d6b656"
          strokeWidth={selected ? 3 : 2}
        />
        <text x="90" y="46" textAnchor="middle" fontSize="11" fontWeight="600" fill="#5d4500">
          {label}
        </text>
        <text x="90" y="60" textAnchor="middle" fontSize="9" fill="#7a5a00">
          (decision)
        </text>
      </svg>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

// ─── Custom Node: Default (rounded rectangle) ─────────────────────────────────
function ProcessNode({ data, selected }: NodeProps) {
  const label = (data as { label: string }).label
  return (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Left} />
      <div
        style={{
          background: '#dae8fc',
          border: `${selected ? 3 : 2}px solid #6c8ebf`,
          borderRadius: 8,
          padding: '10px 14px',
          minWidth: 130,
          textAlign: 'center',
          fontWeight: 600,
          fontSize: 12,
          color: '#1a3a6c',
          whiteSpace: 'pre-line',
        }}
      >
        {label}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { decision: DecisionNode, process: ProcessNode }

// ─── Graph (LR layout) ───────────────────────────────────────────────────────
const nodes: Node[] = [
  { id: 'um', type: 'process', position: { x: 0, y: 180 }, data: { label: 'User\nmessage' } },
  { id: 'hist', type: 'process', position: { x: 220, y: 180 }, data: { label: 'Message history\nMySQL' } },
  { id: 'tc', type: 'process', position: { x: 440, y: 180 }, data: { label: 'Token counter\ncurrent usage' } },
  { id: 'budget', type: 'decision', position: { x: 660, y: 180 }, data: { label: 'Token budget\nHISTORY_MAX_TOKENS=8000' } },
  { id: 'keep', type: 'process', position: { x: 920, y: 40 }, data: { label: 'Keep all\nmessages' } },
  { id: 'summ', type: 'process', position: { x: 920, y: 180 }, data: { label: 'Summarize\nold msgs' } },
  { id: 'cmp', type: 'process', position: { x: 920, y: 320 }, data: { label: 'Compressor\ncompressConversation' } },
  { id: 'sc', type: 'process', position: { x: 1160, y: 180 }, data: { label: 'Summary cache\nin-memory' } },
  { id: 'llm', type: 'process', position: { x: 1400, y: 180 }, data: { label: 'LLM call\ncompressed context' } },
]

const edges: Edge[] = [
  { id: 'um-hist', source: 'um', target: 'hist', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'hist-tc', source: 'hist', target: 'tc', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'tc-budget', source: 'tc', target: 'budget', style: { stroke: '#6c8ebf', strokeWidth: 2 } },
  { id: 'budget-keep', source: 'budget', target: 'keep', label: 'within', style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'budget-summ', source: 'budget', target: 'summ', label: 'approaching', style: { stroke: '#d6b656', strokeWidth: 2 } },
  { id: 'budget-cmp', source: 'budget', target: 'cmp', label: 'exceeded', style: { stroke: '#d62728', strokeWidth: 2 } },
  { id: 'summ-sc', source: 'summ', target: 'sc', style: { stroke: '#d6b656', strokeWidth: 2 } },
  { id: 'sc-cmp', source: 'sc', target: 'cmp', style: { stroke: '#d6b656', strokeWidth: 2 } },
  { id: 'cmp-llm', source: 'cmp', target: 'llm', style: { stroke: '#9673a6', strokeWidth: 2 } },
  { id: 'keep-llm', source: 'keep', target: 'llm', style: { stroke: '#82b366', strokeWidth: 2 } },
]

export function ContextDataFlow() {
  return (
    <div style={{ width: '100%', height: 500 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
      />
    </div>
  )
}

export default ContextDataFlow
