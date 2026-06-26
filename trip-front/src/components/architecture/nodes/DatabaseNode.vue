<script setup lang="ts">
import { Handle, Position, type NodeProps } from '@vue-flow/core'

interface DatabaseNodeData {
  label: string
  sublabel?: string
}

defineProps<NodeProps<DatabaseNodeData>>()
</script>

<template>
  <div class="db-node">
    <svg width="110" height="72" viewBox="0 0 110 72">
      <ellipse cx="55" cy="12" rx="45" ry="8" fill="#ffe6cc" stroke="#d79b00" stroke-width="1.5" />
      <path
        d="M10,12 L10,60 A45,8 0 0 0 100,60 L100,12"
        fill="#ffe6cc"
        stroke="#d79b00"
        stroke-width="1.5"
      />
      <ellipse cx="55" cy="12" rx="45" ry="8" fill="none" stroke="#d79b00" stroke-width="1" opacity="0.4" />
      <ellipse cx="55" cy="36" rx="45" ry="8" fill="none" stroke="#d79b00" stroke-width="1" opacity="0.25" />
      <text x="55" y="40" text-anchor="middle" font-size="11" font-weight="600" fill="#5d3a00">
        {{ data.label }}
      </text>
      <text v-if="data.sublabel" x="55" y="54" text-anchor="middle" font-size="9" fill="#7d5a00">
        {{ data.sublabel }}
      </text>
    </svg>
    <Handle type="target" :position="Position.Top" />
    <Handle type="source" :position="Position.Bottom" />
  </div>
</template>

<style scoped>
.db-node {
  position: relative;
}
</style>
