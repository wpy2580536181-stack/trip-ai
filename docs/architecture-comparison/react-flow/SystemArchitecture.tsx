import { ReactFlow, Handle, Position, type Node, type Edge, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

// ─── Custom Node: Database (cylinder) ─────────────────────────────────────────
function DatabaseNode({ data, selected }: NodeProps) {
  const label = (data as { label: string }).label
  return (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Top} />
      <svg width="120" height="80" viewBox="0 0 120 80">
        <ellipse cx="60" cy="12" rx="50" ry="8" fill="#ffe6cc" stroke="#d79b00" strokeWidth={selected ? 3 : 2} />
        <path
          d="M10,12 L10,62 A50,8 0 0 0 110,62 L110,12"
          fill="#ffe6cc"
          stroke="#d79b00"
          strokeWidth={selected ? 3 : 2}
        />
        <ellipse cx="60" cy="12" rx="50" ry="8" fill="none" stroke="#d79b00" strokeWidth="1" opacity="0.5" />
        <ellipse cx="60" cy="35" rx="50" ry="8" fill="none" stroke="#d79b00" strokeWidth="1" opacity="0.4" />
        <text x="60" y="44" textAnchor="middle" fontSize="11" fontWeight="600" fill="#5d3a00">
          {label}
        </text>
      </svg>
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}

// ─── Custom Node: Cloud (LLM / Embedding) ────────────────────────────────────
function CloudNode({ data, selected }: NodeProps) {
  const label = (data as { label: string }).label
  return (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Left} />
      <svg width="140" height="70" viewBox="0 0 140 70">
        <path
          d="M30,55 Q10,55 10,40 Q10,25 25,25 Q25,12 42,12 Q58,12 62,25 Q70,15 85,18 Q100,15 108,28 Q125,28 128,42 Q130,55 115,55 Z"
          fill="#e1d5e7"
          stroke="#9673a6"
          strokeWidth={selected ? 3 : 2}
        />
        <text x="70" y="40" textAnchor="middle" fontSize="11" fontWeight="600" fill="#3d2c4a">
          {label}
        </text>
      </svg>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

// ─── Custom Node: Default (rectangle) ────────────────────────────────────────
function DefaultNode({ data, selected }: NodeProps) {
  const label = (data as { label: string }).label
  return (
    <div style={{ position: 'relative' }}>
      <Handle type="target" position={Position.Left} />
      <div
        style={{
          background: '#dae8fc',
          border: `${selected ? 3 : 2}px solid #6c8ebf`,
          borderRadius: 8,
          padding: '10px 16px',
          minWidth: 140,
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

const nodeTypes = { database: DatabaseNode, cloud: CloudNode, default: DefaultNode }

// ─── Graph ────────────────────────────────────────────────────────────────────
const nodes: Node[] = [
  {
    id: 'fe',
    type: 'default',
    position: { x: 240, y: 0 },
    data: { label: 'Frontend\nVue 3 + Vite\n+ Pinia + Element Plus' },
  },
  {
    id: 'be',
    type: 'default',
    position: { x: 240, y: 180 },
    data: { label: 'Backend\nExpress 5 + Prisma + Pino' },
  },
  {
    id: 'db',
    type: 'database',
    position: { x: 0, y: 360 },
    data: { label: 'MySQL 8' },
  },
  {
    id: 'rd',
    type: 'database',
    position: { x: 200, y: 360 },
    data: { label: 'Redis 7' },
  },
  {
    id: 'vc',
    type: 'database',
    position: { x: 400, y: 360 },
    data: { label: 'Chroma' },
  },
  {
    id: 'llm',
    type: 'cloud',
    position: { x: 560, y: 180 },
    data: { label: 'DeepSeek\ndeepseek-v4-flash' },
  },
  {
    id: 'emb',
    type: 'cloud',
    position: { x: 560, y: 360 },
    data: { label: 'bge-small-zh\nEmbedding' },
  },
]

const edges: Edge[] = [
  { id: 'fe-be', source: 'fe', target: 'be', label: 'HTTPS REST + SSE', animated: true, style: { stroke: '#1976d2', strokeWidth: 2 } },
  { id: 'be-db', source: 'be', target: 'db', label: 'Prisma ORM', style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'be-rd', source: 'be', target: 'rd', label: 'ioredis', style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'be-vc', source: 'be', target: 'vc', label: 'vector search', style: { stroke: '#82b366', strokeWidth: 2 } },
  { id: 'be-llm', source: 'be', target: 'llm', label: 'chat completion', style: { stroke: '#9673a6', strokeWidth: 2 } },
  { id: 'be-emb', source: 'be', target: 'emb', label: 'embed via LangChain', style: { stroke: '#9673a6', strokeWidth: 2 } },
]

// ─── Component ────────────────────────────────────────────────────────────────
export function SystemArchitecture() {
  return (
    <div style={{ width: '100%', height: 600 }}>
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

export default SystemArchitecture
