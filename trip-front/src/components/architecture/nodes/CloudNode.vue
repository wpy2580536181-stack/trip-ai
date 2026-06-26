<script setup lang="ts">
import { Handle, Position, type NodeProps } from '@vue-flow/core'

interface CloudNodeData {
  label: string
  sublabel?: string
}

defineProps<NodeProps<CloudNodeData>>()
</script>

<template>
  <div class="cloud-node">
    <svg width="130" height="72" viewBox="0 0 130 72">
      <path
        d="M30,58 Q12,58 12,44 Q12,30 28,30 Q28,16 48,16 Q68,16 72,30 Q88,22 102,30 Q118,30 118,44 Q118,58 100,58 Z"
        fill="#e1d5e7"
        stroke="#9673a6"
        stroke-width="1.5"
      />
      <text x="65" y="40" text-anchor="middle" font-size="11" font-weight="600" fill="#3d2c4a">
        {{ data.label }}
      </text>
      <text v-if="data.sublabel" x="65" y="54" text-anchor="middle" font-size="9" fill="#5d3c6a">
        {{ data.sublabel }}
      </text>
    </svg>
    <Handle type="target" :position="Position.Left" />
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<style scoped>
.cloud-node {
  position: relative;
}
</style>
