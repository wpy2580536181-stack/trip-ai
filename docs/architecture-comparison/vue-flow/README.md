# Vue Flow 架构图

> 4 张可交互架构图，基于 [Vue Flow](https://vueflow.dev)（@vue-flow/core）。
> 源码真相仍是 [`../../architecture-diagrams.md`](../../architecture-diagrams.md) 的 Mermaid。
> 这是 [`../react-flow/`](../react-flow/) 的 Vue 3 对照版。

---

## 什么是 Vue Flow

Vue Flow 是 React Flow 的 Vue 3 移植版。声明式地定义 `nodes` 和 `edges`，得到可缩放、可拖拽的画布。`@vue-flow/core` 是其开源包名。

## 适用场景（与 React Flow 完全一样）

- 把架构图**嵌进产品**（后台管理、文档站点、devtools 面板）
- 需要**点击节点跳详情**、悬浮显示实时指标、拖拽重构拓扑
- 想要**自定义节点**（圆柱、菱形、复合卡片）

> **前端栈选择**：trip-front 已经是 Vue 3 + Vite，所以这里用 Vue Flow 比 React Flow 更自然（不用再拉 React 运行时）。

## 与 Mermaid 相比

| 维度 | Mermaid | Vue Flow |
|------|---------|----------|
| 写起来 | 几行声明 | 几十到几百行 SFC |
| GitHub 渲染 | 原生支持 | 不支持（需要 dev server / 截图） |
| 交互性 | 只读 | 可拖拽、可缩放、可编辑 |
| 嵌入产品 | 困难 | 天生为组件 |
| 序列图 | 一等公民 | 需要 SVG overlay 强行画 |
| 自定义节点 | 有限（subgraph） | 完全自由（任意 Vue 组件） |

## 优 / 劣

### ✅ 优势

- **Vue 3 原生** — `<script setup lang="ts">` + `computed` 写自定义节点很顺
- **可拖拽** — 节点位置可在 UI 上调整并保存回状态
- **可嵌入** — 直接作为 SFC 放进 `trip-front/src/components/architecture/`
- **完全可定制** — 节点可以是任意 Vue 组件
- **运行时比 React Flow 轻** — Vue 3 reactive 比 React 重渲染模型更适合"频繁位置更新"

### ❌ 劣势

- **需要构建步骤** — `npm i @vue-flow/core` 后才能跑
- **序列图非常别扭** — AgentSequence.vue 用 SVG `<template>` overlay 强行画 message arrows
- **4-10x 代码量** — 同一张图 Mermaid 10 行，Vue Flow 80+ 行
- **位置是手填像素** — 没有 dagre/elk 自动布局
- **GitHub 不渲染** — PR review 看图必须跑项目
- **生态比 React Flow 小** — 第三方节点/插件少

## 在 trip-ai 里怎么用

```bash
cd trip-front
npm i @vue-flow/core
```

然后：

```vue
<!-- trip-front/src/pages/Architecture.vue -->
<script setup lang="ts">
import SystemArchitecture from '@/components/architecture/SystemArchitecture.vue'
import AgentSequence from '@/components/architecture/AgentSequence.vue'
import ContextDataFlow from '@/components/architecture/ContextDataFlow.vue'
import EvaluationSystem from '@/components/architecture/EvaluationSystem.vue'
</script>

<template>
  <div>
    <h1>System Architecture</h1>
    <SystemArchitecture />
    <h1>Agent Sequence</h1>
    <AgentSequence />
    <!-- ... -->
  </div>
</template>
```

文件复制目标路径：

```
trip-front/src/components/architecture/
├── SystemArchitecture.vue
├── AgentSequence.vue
├── ContextDataFlow.vue
└── EvaluationSystem.vue
```

## 4 张图一览

| 文件 | 布局 | 自定义节点 | 复杂度 |
|------|------|-----------|--------|
| `SystemArchitecture.vue` | TB | DatabaseNode（圆柱）、CloudNode（云朵）、DefaultNode | 中 |
| `AgentSequence.vue` | Swimlane + SVG overlay | ActorNode（粗色条） | 高 ⚠ |
| `ContextDataFlow.vue` | LR | DecisionNode（菱形）、ProcessNode | 低 |
| `EvaluationSystem.vue` | TB | GroupNode（2x2 网格）、ProcessNode | 中 |

## 与 React Flow 版的差异

- **节点定义** — `type: Node[]` 在 `<script setup>` 里是普通 TS，`<VueFlow :nodes="...">` 接收
- **自定义节点** — 用函数式组件 `(props: NodeProps) => () => VNode`，比 React 略繁琐（要写 `() =>` 返回函数 + `computed`）
- **样式 props** — `:style` 在 Vue 是 object，React 是 object —— 一样的
- **Handle** — `import { Handle, Position }` 用法几乎相同

## 一个 Mermaid 做不到的事

**点击节点弹出该服务的实时指标卡片**（P99 延迟、QPS、错误率）。把节点 `@click` 接上后端 `/api/metrics?service=X`，Vue Flow 让你在"看图"和"运维台"之间无缝切换 —— Mermaid 是静态图，做不到这种"活的系统拓扑"。

> **额外甜点**：Vue 3 的 `reactive` 节点数组天然支持"实时拓扑" —— 某个服务挂了，边变红；流量上涨，节点变粗。所有这些都能在 Mermaid 里要重画图完成。

## 注意事项

1. **位置是手填的** — x/y 是像素值，改完节点数要重新对齐
2. **fit-view-on-init** — 容器需要明确高度
3. **Custom node 必须返回函数** — `() => VNode` 而非 `VNode`，否则 props 不会响应
4. **TypeScript 严格模式** — `ACTOR_X[m.target]!` 这种 `!` 是因为 index signature 不推断，介意可以改成 `Record<string, number>` + helper
5. **不要把这里当组件库** — 这是参考实现；接到产品里要拆 props、加 dark mode、抽常量
