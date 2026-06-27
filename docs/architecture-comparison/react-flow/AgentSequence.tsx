import { ReactFlow, Handle, Position, type Node, type Edge, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'

// ─── Custom Node: Actor (tall header bar) ─────────────────────────────────────
function ActorNode({ data }: NodeProps) {
  const { label, color } = data as { label: string; color: string }
  return (
    <div
      style={{
        background: color,
        color: '#fff',
        padding: '12px 8px',
        borderRadius: 6,
        textAlign: 'center',
        fontWeight: 700,
        fontSize: 12,
        width: 110,
        minHeight: 50,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
      }}
    >
      {label}
    </div>
  )
}

// ─── Custom Edge: Sequence message with number ────────────────────────────────
type SeqEdgeData = { num: number; dashed?: boolean }
function SequenceEdge(props: { data?: SeqEdgeData; sourceX: number; sourceY: number; targetX: number; targetY: number }) {
  const { data, sourceX, sourceY, targetX, targetY } = props
  const dx = targetX - sourceX
  const isReverse = dx < 0
  const stroke = isReverse ? '#d62728' : '#1976d2'
  const dashArray = data?.dashed ? '6 4' : undefined
  return (
    <>
      <defs>
        <marker
          id={`arrow-${stroke}`}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L10,5 L0,10 z" fill={stroke} />
        </marker>
      </defs>
      <line
        x1={sourceX}
        y1={sourceY}
        x2={targetX}
        y2={targetY}
        stroke={stroke}
        strokeWidth={2}
        strokeDasharray={dashArray}
        markerEnd={`url(#arrow-${stroke})`}
      />
      {data?.num != null && (
        <circle cx={sourceX + dx / 2} cy={(sourceY + targetY) / 2} r={10} fill="#fff" stroke={stroke} strokeWidth={1.5} />
      )}
      {data?.num != null && (
        <text
          x={sourceX + dx / 2}
          y={(sourceY + targetY) / 2 + 4}
          textAnchor="middle"
          fontSize="11"
          fontWeight="700"
          fill={stroke}
        >
          {data.num}
        </text>
      )}
    </>
  )
}

const nodeTypes = { actor: ActorNode }

// 7 actor columns at x = 60, 220, 380, 540, 700, 860, 1020
const ACTOR_X = { U: 60, FE: 220, BE: 380, AE: 540, L: 700, T: 860, DB: 1020 } as const
const HEADER_Y = 0
const LIFELINE_GAP = 600 // visual hint; lifeline is not a node

const nodes: Node[] = [
  { id: 'U', type: 'actor', position: { x: ACTOR_X.U, y: HEADER_Y }, data: { label: 'User', color: '#6c8ebf' } },
  { id: 'FE', type: 'actor', position: { x: ACTOR_X.FE, y: HEADER_Y }, data: { label: 'Frontend', color: '#6c8ebf' } },
  { id: 'BE', type: 'actor', position: { x: ACTOR_X.BE, y: HEADER_Y }, data: { label: 'tripService', color: '#82b366' } },
  { id: 'AE', type: 'actor', position: { x: ACTOR_X.AE, y: HEADER_Y }, data: { label: 'AgentEngine', color: '#82b366' } },
  { id: 'L', type: 'actor', position: { x: ACTOR_X.L, y: HEADER_Y }, data: { label: 'LLM (DeepSeek)', color: '#9673a6' } },
  { id: 'T', type: 'actor', position: { x: ACTOR_X.T, y: HEADER_Y }, data: { label: 'Tool', color: '#d6b656' } },
  { id: 'DB', type: 'actor', position: { x: ACTOR_X.DB, y: HEADER_Y }, data: { label: 'MySQL', color: '#d79b00' } },
]

// Lifelines (rendered as edges from each actor header going down)
const edges: Edge[] = [
  // lifelines
  { id: 'life-U', source: 'U', target: 'U', type: 'default', style: { stroke: '#999', strokeDasharray: '4 4' } },
  { id: 'life-FE', source: 'FE', target: 'FE', type: 'default', style: { stroke: '#999', strokeDasharray: '4 4' } },
  { id: 'life-BE', source: 'BE', target: 'BE', type: 'default', style: { stroke: '#999', strokeDasharray: '4 4' } },
  { id: 'life-AE', source: 'AE', target: 'AE', type: 'default', style: { stroke: '#999', strokeDasharray: '4 4' } },
  { id: 'life-L', source: 'L', target: 'L', type: 'default', style: { stroke: '#999', strokeDasharray: '4 4' } },
  { id: 'life-T', source: 'T', target: 'T', type: 'default', style: { stroke: '#999', strokeDasharray: '4 4' } },
  { id: 'life-DB', source: 'DB', target: 'DB', type: 'default', style: { stroke: '#999', strokeDasharray: '4 4' } },
]

// Sequence numbers mapped to message steps (vertical y positions via edge label offsets)
const messages: Array<{
  id: string
  num: number
  source: keyof typeof ACTOR_X
  target: keyof typeof ACTOR_X
  label: string
  dashed?: boolean
}> = [
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

export function AgentSequence() {
  // We render the message edges manually as SVG annotations on top of the React Flow viewport
  return (
    <div style={{ width: '100%', height: 700, position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
      />
      <MessageOverlay messages={messages} />
      <SequenceCaveat />
    </div>
  )
}

// ─── Message overlay (SVG drawn on top of the canvas) ─────────────────────────
function MessageOverlay({
  messages,
}: {
  messages: Array<{ id: string; num: number; source: keyof typeof ACTOR_X; target: keyof typeof ACTOR_X; label: string; dashed?: boolean }>
}) {
  // Vertical spacing for messages; lifelines visible roughly y=80..680
  const startY = 100
  const stepY = 36
  return (
    <svg
      style={{ position: 'absolute', inset: 0, pointerEvents: 'none', width: '100%', height: '100%' }}
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
      {messages.map((m, i) => {
        const y = startY + i * stepY
        const x1 = ACTOR_X[m.source] + 55
        const x2 = ACTOR_X[m.target] + 55
        const isReverse = x2 < x1
        const stroke = isReverse ? '#d62728' : '#1976d2'
        const marker = isReverse ? 'arrow-red' : 'arrow-blue'
        const dash = m.dashed ? '6 4' : undefined
        return (
          <g key={m.id}>
            <line x1={x1} y1={y} x2={x2} y2={y} stroke={stroke} strokeWidth={1.8} strokeDasharray={dash} markerEnd={`url(#${marker})`} />
            <circle cx={(x1 + x2) / 2} cy={y} r={10} fill="#fff" stroke={stroke} strokeWidth={1.5} />
            <text x={(x1 + x2) / 2} y={y + 4} textAnchor="middle" fontSize="10" fontWeight="700" fill={stroke}>
              {m.num}
            </text>
            <text
              x={(x1 + x2) / 2}
              y={y - 6}
              textAnchor="middle"
              fontSize="10"
              fill="#333"
              style={{ paintOrder: 'stroke', stroke: '#fff', strokeWidth: 3 }}
            >
              {m.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function SequenceCaveat() {
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 8,
        right: 12,
        background: 'rgba(255, 244, 196, 0.95)',
        border: '1px solid #d6b656',
        borderRadius: 4,
        padding: '4px 10px',
        fontSize: 11,
        color: '#6b4f00',
      }}
    >
      ⚠ React Flow is not ideal for sequence diagrams — messages drawn via SVG overlay above the actor headers.
    </div>
  )
}

export default AgentSequence
