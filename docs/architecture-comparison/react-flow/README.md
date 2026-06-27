# React Flow 架构图

> 4 张可交互架构图，基于 [React Flow](https://reactflow.dev)（@xyflow/react v12）。
> 源码真相仍是 [`../../architecture-diagrams.md`](../../architecture-diagrams.md) 的 Mermaid。

---

## 什么是 React Flow

React Flow 是为 React 写的**节点编辑器库**。你声明一组 `nodes` 和连接它们的 `edges`，它就给你一个可缩放、可拖拽、可连接的画布。`@xyflow/react` 是其开源包名。

## 适用场景

- 想把架构图**嵌进产品里**（后台管理、文档站点、devtools 面板）
- 需要**点击节点跳详情**、悬浮显示实时指标、拖拽重构拓扑
- 想要**自定义节点**（圆柱、菱形、复合卡片）

## 与 Mermaid 相比

| 维度 | Mermaid | React Flow |
|------|---------|------------|
| 写起来 | 几行声明 | 几十到几百行 TSX |
| GitHub 渲染 | 原生支持 | 不支持（需要 dev server / 截图） |
| 交互性 | 只读 | 可拖拽、可缩放、可编辑 |
| 嵌入产品 | 困难 | 天生为组件 |
| 序列图 | 一等公民 | 需要 SVG overlay 强行画 |
| 自定义节点 | 有限（subgraph） | 完全自由（任意 React 组件） |

## 优 / 劣

### ✅ 优势

- **可拖拽** — 节点位置可在 UI 上调整并保存回状态
- **可嵌入** — 直接作为 React 组件放进 `trip-front/src/components/architecture/`
- **完全可定制** — 节点可以是任意 React 组件（这里 DatabaseNode/CloudNode/DecisionNode/GroupNode 都是 SVG + 文字的组合）
- **可编程** — `onNodeClick`、`onConnect` 等回调让图成为"活"的 UI

### ❌ 劣势

- **需要构建步骤** — `npm i @xyflow/react` 后才能跑
- **序列图非常别扭** — ActorSequence.tsx 用 SVG overlay 强行画 message arrows，可读性差、维护成本高
- **4-10x 代码量** — 同一张图 Mermaid 10 行，React Flow 80+ 行
- **位置是手填像素** — 没有 dagre/elk 自动布局（可加 `dagre` 包但复杂度更高）
- **GitHub 不渲染** — PR review 看图必须跑项目

## 在 trip-ai 里怎么用

```bash
cd trip-front
npm i @xyflow/react
```

然后：

```tsx
// trip-front/src/pages/Architecture.tsx
import { SystemArchitecture } from '@/components/architecture/SystemArchitecture'
import { AgentSequence } from '@/components/architecture/AgentSequence'
import { ContextDataFlow } from '@/components/architecture/ContextDataFlow'
import { EvaluationSystem } from '@/components/architecture/EvaluationSystem'

export default function Architecture() {
  return (
    <div>
      <h1>System Architecture</h1>
      <SystemArchitecture />
      <h1>Agent Sequence</h1>
      <AgentSequence />
      {/* ... */}
    </div>
  )
}
```

文件复制目标路径：

```
trip-front/src/components/architecture/
├── SystemArchitecture.tsx
├── AgentSequence.tsx
├── ContextDataFlow.tsx
└── EvaluationSystem.tsx
```

## 4 张图一览

| 文件 | 布局 | 自定义节点 | 复杂度 |
|------|------|-----------|--------|
| `SystemArchitecture.tsx` | TB | DatabaseNode（圆柱）、CloudNode（云朵）、DefaultNode | 中 |
| `AgentSequence.tsx` | Swimlane + SVG overlay | ActorNode（粗色条） | 高 ⚠ |
| `ContextDataFlow.tsx` | LR | DecisionNode（菱形）、ProcessNode | 低 |
| `EvaluationSystem.tsx` | TB | GroupNode（2x2 网格）、ProcessNode | 中 |

## 一个 Mermaid 做不到的事

**点击节点弹出该服务的实时指标卡片**（P99 延迟、QPS、错误率）。把节点 onClick 接上后端 `/api/metrics?service=X`，React Flow 让你在"看图"和"运维台"之间无缝切换 —— Mermaid 是静态图，做不到这种"活的系统拓扑"。

## 注意事项

1. **位置是手填的** — x/y 是像素值，diagram 改完节点数要重新对齐。本目录里我把节点拉到 100px 网格方便调整。
2. **fitView** — 容器需要有明确高度（`height: 600` 之类），否则画布不显示。
3. **Custom node 的 `<Handle>`** — React Flow 用 `Handle` 声明连接点；位置 `Position.Top/Bottom/Left/Right` 决定边的进出方向。
4. **proOptions.hideAttribution** — 商业项目推荐关掉左下角水印（@xyflow/react 是 MIT，但展示更干净）。
5. **不要把这里当组件库** — 这是参考实现；接到产品里要拆 props、加 dark mode、抽常量。
