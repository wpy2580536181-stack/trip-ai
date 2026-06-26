<script setup lang="ts">
import { Handle, Position, type NodeProps } from '@vue-flow/core'

interface ServiceNodeData {
  label: string
  sublabel?: string
  color?: string
}

const props = defineProps<NodeProps<ServiceNodeData>>()

function darken(hex: string, amount = 0.7): string {
  if (!hex || hex[0] !== '#' || hex.length !== 7) return '#6c8ebf'
  const r = Math.floor(parseInt(hex.slice(1, 3), 16) * amount)
  const g = Math.floor(parseInt(hex.slice(3, 5), 16) * amount)
  const b = Math.floor(parseInt(hex.slice(5, 7), 16) * amount)
  return `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`
}

const bg = () => props.data?.color || '#dae8fc'
const border = () => darken(props.data?.color || '#dae8fc')
</script>

<template>
  <div
    class="service-node"
    :style="{
      background: bg(),
      border: '1.5px solid ' + border(),
    }"
  >
    <div class="label">{{ data.label }}</div>
    <div v-if="data.sublabel" class="sublabel">{{ data.sublabel }}</div>
    <Handle type="target" :position="Position.Top" />
    <Handle type="source" :position="Position.Bottom" />
  </div>
</template>

<style scoped>
.service-node {
  position: relative;
  padding: 10px 16px;
  border-radius: 8px;
  min-width: 130px;
  text-align: center;
  font-size: 12px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
}
.label {
  font-weight: 600;
  color: #1a1a1a;
  line-height: 1.3;
}
.sublabel {
  font-size: 10px;
  color: #555;
  margin-top: 3px;
}
</style>
